from django import forms
from django.contrib import messages
from django.contrib.auth import login as django_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView, FormView
from sesame.views import LoginView as SesameLoginView

from totem.email import emails
from totem.utils.slack import notify_slack

from .forms import LoginForm
from .models import User


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "slug"
    slug_url_kwarg = "slug"


user_detail_view = UserDetailView.as_view()


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "email")


@login_required
def user_update_view(request, *args, **kwargs):
    user = request.user
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
            return redirect("users:dashboard")
    return render(request, "users/user_form.html", {"form": form})


@login_required
def user_redirect_view(request, *args, **kwargs):
    user = request.user
    assert user.is_authenticated
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
            messages.success(self.request, "Email successfully verified!")
        return super().login_success()


class LogInView(FormView):
    template_name = "users/login.html"
    form_class = LoginForm
    success_url = reverse_lazy("users:login")

    def _message(self, email: str):
        messages.success(self.request, f"Please check your inbox at: {email}.")

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


def _notify_slack():
    notify_slack("Signup: A new person has signed up for ✨Totem✨!")


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
        emails.send_new_login_email(user.email, url)
        _notify_slack()
    else:
        emails.send_returning_login_email(user.email, url)

    user.identify()  # type: ignore
    return created


def user_index_view(request):
    return user_redirect_view(request)


@login_required
def user_dashboard_view(request):
    return render(request, "users/dashboard.html", context={"object": request.user})


@login_required
def user_profile_view(request):
    subscribed_circles = request.user.subscribed_circles.all()
    circle_history = request.user.events_joined.all()
    return render(
        request,
        "users/profile.html",
        context={"object": request.user, "subscribed_circles": subscribed_circles, "circle_history": circle_history},
    )


@login_required
def user_profile_info_view(request):
    user = request.user
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
            return redirect("users:profile")
    return render(request, "users/profile_info.html", {"form": form})


@login_required
def user_profile_notifications_view(request):
    subscribed_circles = request.user.subscribed_circles.all()
    return render(
        request,
        "users/profile_notifications.html",
        context={"object": request.user, "subscribed_circles": subscribed_circles},
    )


@login_required
def user_profile_delete_view(request):
    if request.method == "POST":
        user = request.user
        user.delete()
        messages.success(request, "Account successfully deleted.")
        return redirect("pages:home")
    return render(request, "users/profile_delete.html", context={"object": request.user})
