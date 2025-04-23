from auditlog.context import disable_auditlog
from auditlog.models import LogEntry
from django import forms
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from totem.circles.filters import all_upcoming_recommended_events, upcoming_attending_events, upcoming_events_by_author
from totem.email import emails
from totem.utils.slack import notify_slack

from . import analytics
from .forms import LoginForm, SignupForm
from .models import Feedback, KeeperProfile, LoginPin, User


def user_detail_view(request, slug):
    try:
        user = User.objects.get(slug=slug)
        if user.keeper_profile:
            events = upcoming_events_by_author(request.user, user)[:10]
            circle_count = user.events_joined.count()
            return render(
                request,
                "users/user_detail.html",
                context={"user": user, "events": events, "profile": user.keeper_profile, "circle_count": circle_count},
            )
    except (User.DoesNotExist, ObjectDoesNotExist):
        pass
    raise Http404


def profiles(request, name):
    try:
        user = KeeperProfile.objects.get(username=name).user
        if user.keeper_profile:
            events = upcoming_events_by_author(request.user, user)[:10]
            circle_count = user.events_joined.count()
            return render(
                request,
                "users/user_detail.html",
                context={"user": user, "events": events, "profile": user.keeper_profile, "circle_count": circle_count},
            )
    except KeeperProfile.DoesNotExist:
        pass
    raise Http404


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "email", "timezone")


class UserConsentForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("newsletter_consent",)
        formfield_callback = lambda f: f.formfield(template_name="fields/checkbox.html")  # noqa: E731


@login_required
def user_redirect_view(request, *args, **kwargs):
    user = request.user
    try:
        if user.onboard and user.onboard.onboarded:
            next = request.session.get("next")
            if next:
                del request.session["next"]
                if url_has_allowed_host_and_scheme(next, None):
                    return redirect(next)
            return redirect("users:dashboard")
    except ObjectDoesNotExist:
        pass
    return redirect("onboard:index")


class PinVerifyForm(forms.Form):
    pin = forms.CharField(max_length=6, min_length=6)
    email = forms.EmailField()


@transaction.atomic
def verify_pin_view(request: HttpRequest):
    if request.method == "POST":
        form = PinVerifyForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            pin = form.cleaned_data["pin"]
            try:
                user = User.objects.get(email=email)

                # Check if account is deactivated
                if not user.is_active:
                    return redirect("users:deactivated")

                is_valid, pin_obj = LoginPin.objects.validate_pin(user, pin)

                if is_valid:
                    auth_login(request, user)

                    if not user.verified:
                        user.verified = True
                        user.save()

                    # Get redirect URL from session or default (now only 'next')
                    next_url = request.session.pop("next", None)
                    if not next_url or not url_has_allowed_host_and_scheme(next_url, None):
                        next_url = "users:redirect"

                    # ENFORCE ONBOARDING
                    if not getattr(user, "onboard", None) or not getattr(user.onboard, "onboarded", False):
                        return redirect(f"{reverse('onboard:index')}?next={next_url}")

                    return redirect(next_url)

                # Use generic error message to avoid revealing if email exists
                form.add_error(None, "Invalid or expired verification code. Please try again or request a new code.")
            except User.DoesNotExist:
                # Use same generic error to avoid revealing if email exists
                form.add_error(None, "Invalid or expired verification code. Please try again or request a new code.")
    else:
        form = PinVerifyForm()
        if "email" in request.GET:
            form = PinVerifyForm(initial={"email": request.GET["email"]})

    return render(request, "users/verify_pin.html", {"form": form})


def login_view(request: HttpRequest):
    return _auth_view(request, LoginForm, "users/login.html")


def signup_view(request: HttpRequest):
    return _auth_view(request, SignupForm, "users/signup.html")


def user_deactivated_view(request: HttpRequest):
    return render(request, "users/deactivated.html")


def _auth_view(request: HttpRequest, form_class: type[forms.Form], template_name: str):
    next = request.GET.get("next")
    if not url_has_allowed_host_and_scheme(next, None):
        next = None
    context = {"next": next}
    if request.POST:
        form = form_class(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            email: str = data["email"].lower()
            # Only use 'next' as the post-auth redirect parameter
            create_params = {"newsletter_consent": data.get("newsletter_consent", False)}

            # Create or get user
            user, created = User.objects.get_or_create(email=email, defaults=create_params or {})

            # Check if account is deactivated
            if not user.is_active:
                return redirect("users:deactivated")

            # Generate PIN and continue with login process
            login_pin = LoginPin.objects.generate_pin(user)

            # Store 'next' in session for redirect after validation
            if next:
                request.session["next"] = next

            # Send PIN via email
            emails.login_pin_email(user.email, login_pin.pin).send()

            if created:
                emails.welcome_email(user).send()
                analytics.user_signed_up(user)

            user.identify()
            return redirect(f"{reverse('users:verify-pin')}?email={email}")
    else:
        if request.user.is_authenticated:
            return redirect(next or "users:redirect")
        if next:
            request.session["next"] = next
        form = form_class()
    response = render(request, template_name, context=context | {"form": form})
    return response


def user_index_view(request):
    return user_redirect_view(request)


@login_required
def user_dashboard_view(request):
    user: User = request.user
    attending_events = upcoming_attending_events(user, limit=10)
    recommended_events = all_upcoming_recommended_events(user)[:4]

    return render(
        request,
        "users/dashboard.html",
        context={"user": user, "attending_events": attending_events, "recommended_events": recommended_events},
    )


@login_required
def user_profile_view(request):
    subscribed_circles = request.user.subscribed_circles.all()[0:10]
    circle_history_query = request.user.events_joined.order_by("-start")
    circle_history = circle_history_query.all()[0:10]
    circle_count = circle_history_query.count()
    context = {
        "object": request.user,
        "subscribed_circles": subscribed_circles,
        "circle_history": circle_history,
        "circle_count": circle_count,
    }
    context.update(_user_profile_info(request, request.user))
    return render(
        request,
        "users/profile.html",
        context=context,
    )


def _user_profile_info(request, user: User):
    form = UserUpdateForm(instance=user)
    consent_form = UserConsentForm(instance=user)
    if request.method == "POST":
        old_email = user.email
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            new_email = form.cleaned_data["email"]
            if old_email != new_email:
                user.email = new_email
                user.verified = False
                user.save()
            form.save()
            messages.success(request, "Profile successfully updated.")
        consent_form = UserConsentForm(request.POST, instance=user)
        if consent_form.is_valid():
            consent_form.save()
    return {"info_form": form, "consent_form": consent_form}


class ProfileForm(forms.ModelForm):
    profile_avatar_type = forms.ChoiceField(
        required=False,
        choices=User.ProfileChoices.choices,
    )
    profile_image = forms.ImageField(
        required=False,
    )
    randomize = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ("profile_avatar_type", "profile_image")


@login_required
def user_profile_image_view(request):
    user = request.user
    form = ProfileForm(request.POST, request.FILES, instance=user)
    if request.method == "POST":
        if form.is_valid():
            if form.cleaned_data["randomize"]:
                user.randomize_avatar()
            form.save()
    return render(
        request,
        "users/profile/_profile_image_edit.html",
        context={"choices": User.ProfileChoices.choices, "user": request.user, "form": form},
    )


@login_required
def user_profile_delete_view(request):
    if request.method == "POST":
        user = request.user
        # make a log entry for the deletion
        LogEntry.objects.log_create(user, force_log=True, action=LogEntry.Action.DELETE).save()  # type: ignore
        with disable_auditlog():
            user.delete()
        messages.success(request, "Account successfully deleted.")
        return redirect("pages:home")
    return HttpResponseForbidden()


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ("email", "message")
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5, "cols": 15}),
        }


FEEDBACK_SUCCESS_MESSAGE = "Feedback successfully submitted. Thank you!"


def user_feedback_view(request):
    banned_words = ["USD"]
    form = FeedbackForm()
    if request.method == "POST":
        data = request.POST.copy()
        form = FeedbackForm(data)
        if form.is_valid():
            cleaned = form.cleaned_data
            is_spam = any(word in cleaned["message"] for word in banned_words)
            if request.user.is_authenticated:
                name = request.user.name
                Feedback.objects.create(**cleaned, user=request.user)
            else:
                name = "Anonymous"
                Feedback.objects.create(**cleaned)
            messages.success(request, FEEDBACK_SUCCESS_MESSAGE)
            if not is_spam:
                notify_slack(f"Feedback from {name}! \nMessage: \n{form.cleaned_data['message']}")
            form = FeedbackForm()
    return render(request, "users/feedback.html", context={"form": form})
