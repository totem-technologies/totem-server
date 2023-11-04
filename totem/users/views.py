from django import forms
from django.contrib import messages
from django.contrib.auth import login as django_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import FormView
from sesame.views import LoginView as SesameLoginView

from totem.circles.filters import upcoming_events_user_can_attend
from totem.email import emails
from totem.utils.slack import notify_slack

from . import analytics
from .forms import LoginForm
from .models import Feedback, User


def user_detail_view(request, slug):
    try:
        user = User.objects.get(slug=slug)
        if user.keeper_profile:
            events = [e.next_event() for e in user.created_circles.all()[:10] if e.next_event()]
            return render(request, "users/user_detail.html", context={"user": user, "events": events})
    except (User.DoesNotExist, ObjectDoesNotExist):
        pass
    raise Http404


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "email", "timezone")


@login_required
def user_redirect_view(request, *args, **kwargs):
    user = request.user
    try:
        if user.onboard and user.onboard.onboarded:
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


class LogInView(FormView):
    template_name = "users/login.html"
    form_class = LoginForm
    success_url = reverse_lazy("users:login")

    def _message(self, email: str):
        messages.success(self.request, f"Please check your inbox at: {email}.")

    def get(self, request: HttpRequest, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Make sure htmx redirects to the login page with a full refresh
        response.headers["HX-Redirect"] = request.get_full_path()  # type: ignore
        return response

    def form_valid(self, form):
        success_url = form.cleaned_data.get("success_url")
        email = form.cleaned_data["email"].lower()
        after_login_url = form.cleaned_data.get("after_login_url") or self.request.GET.get("next")
        created = login(email, self.request, after_login_url=after_login_url)
        if success_url:
            self.success_url = success_url
        elif created:
            self.success_url = reverse("users:redirect")
        if not created:
            self._message(email)
        return super().form_valid(form)


def login(email: str, request, after_login_url: str | None = None, mobile: bool = False) -> bool:
    """Login a user by sending them a login link via email. If it's a new user, log them in automatically and send them
    a welcome email.

    Args:
        email (str): The email address to send the login link to.
        after_login_url (str, optional): The URL to redirect to after the user logs in. Defaults to None.
    """
    user, created = User.objects.get_or_create(email=email)

    url = user.get_login_url(after_login_url, mobile)  # type: ignore

    if created:
        django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        # TODO make new welcome email. This one expires after 30min and doesn't make sense for a new user.
        # emails.send_new_login_email(user.email, url)
        analytics.user_signed_up(user)
    else:
        emails.send_returning_login_email(user.email, url)

    user.identify()  # type: ignore
    return created


def user_index_view(request):
    return user_redirect_view(request)


@login_required
def user_dashboard_view(request):
    user: User = request.user
    now_plus_60 = timezone.now() + timezone.timedelta(minutes=60)
    attending_events = user.events_attending.filter(start__gte=now_plus_60).filter(cancelled=False).order_by("start")
    recommended_events = upcoming_events_user_can_attend(user)
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
    if request.method == "POST":
        old_email = user.email
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            message = "Profile successfully updated."
            new_email = form.cleaned_data["email"]
            if old_email != new_email:
                login_url = user.get_login_url(after_login_url=None, mobile=False)
                user.verified = False
                emails.send_change_email(old_email, new_email, login_url)
                message = f"Email successfully updated to {new_email}. Please check your inbox to confirm."
            form.save()
            messages.success(request, message)
    return {"info_form": form}


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


def user_feedback_view(request):
    form = FeedbackForm()
    if request.method == "POST":
        data = request.POST.copy()
        form = FeedbackForm(data)
        if form.is_valid():
            if request.user.is_authenticated:
                name = request.user.name
                Feedback.objects.create(**form.cleaned_data, user=request.user)
            else:
                name = "Anonymous"
                Feedback.objects.create(**form.cleaned_data)
            messages.success(request, "Feedback successfully submitted. Thank you!")
            notify_slack(f"Feedback from {name}! \nMessage: \n{form.cleaned_data['message']}")
            form = FeedbackForm()
    return render(request, "users/feedback.html", context={"form": form})
