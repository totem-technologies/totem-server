from auditlog.context import disable_auditlog
from auditlog.models import LogEntry
from django import forms
from django.contrib import messages
from django.contrib.auth import login as django_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from sesame.views import LoginView as SesameLoginView

from totem.circles.filters import all_upcoming_recommended_events, upcoming_attending_events, upcoming_events_by_author
from totem.email import emails
from totem.utils.slack import notify_slack

from . import analytics
from .forms import LoginForm, SignupForm
from .models import Feedback, KeeperProfile, User


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
    # newsletter_consent = forms.BooleanField(template_name="fields/checkbox.html", required=False)  # type: ignore

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


class MagicLoginView(SesameLoginView):
    def login_success(self):
        user = self.request.user
        if not user.verified:  # type: ignore
            user.verified = True  # type: ignore
            user.save()
        return super().login_success()


def login_view(request: HttpRequest):
    return _auth_view(request, LoginForm, "users/login.html")


def signup_view(request: HttpRequest):
    return _auth_view(request, SignupForm, "users/signup.html")


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
            after_login_url: str = data.get("after_login_url", next)
            create_params = {"newsletter_consent": data.get("newsletter_consent", False)}
            created = login(request, email=email, create_params=create_params, after_login_url=after_login_url)
            if created:
                return redirect("users:redirect")
            else:
                messages.success(request, f"Please check your inbox at: {email}.")
                path = request.get_full_path()
                if url_has_allowed_host_and_scheme(path, None):
                    return redirect(path)
                else:
                    return redirect("users:redirect")
    else:
        if request.user.is_authenticated:
            return redirect(next or "users:redirect")
        if next:
            request.session["next"] = next
        form = form_class()
    response = render(request, template_name, context=context | {"form": form})
    # Make sure htmx redirects to the login page with a full refresh
    response.headers["HX-Redirect"] = request.get_full_path()  # type: ignore
    return response


@transaction.atomic
def login(
    request, *, email: str, create_params: dict | None = None, after_login_url: str | None = None, mobile: bool = False
) -> bool:
    """Login a user by sending them a login link via email. If it's a new user, log them in automatically and send them
    a welcome email.

    Args:
        email (str): The email address to send the login link to.
        after_login_url (str, optional): The URL to redirect to after the user logs in. Defaults to None.
    """
    user, created = User.objects.get_or_create(email=email, defaults=create_params or {})

    url = user.get_login_url(after_login_url, mobile)  # type: ignore

    if created:
        django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        emails.welcome_email(user).send()
        analytics.user_signed_up(user)
    else:
        emails.returning_login_email(user.email, url).send()

    user.identify()  # type: ignore
    return created


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
            message = "Profile successfully updated."
            new_email = form.cleaned_data["email"]
            if old_email != new_email:
                login_url = user.get_login_url(after_login_url=None, mobile=False)
                user.verified = False
                emails.change_email(old_email, new_email, login_url).send()
                message = f"Email successfully updated to {new_email}. Please check your inbox to confirm."
            form.save()
            messages.success(request, message)
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
