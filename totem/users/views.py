from typing import Optional

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse, reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, FormView, RedirectView, UpdateView
from sesame.utils import get_query_string

from totem.email.utils import send_mail

from .forms import LoginForm

User = get_user_model()


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "id"
    slug_url_kwarg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        assert self.request.user.is_authenticated  # for mypy to know that the user is authenticated
        return self.request.user.get_absolute_url()  # type: ignore

    def get_object(self):
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        return reverse("users:detail", kwargs={"pk": self.request.user.pk})


user_redirect_view = UserRedirectView.as_view()


class LogInView(FormView):
    template_name = "users/login.html"
    form_class = LoginForm
    success_url = reverse_lazy("users:login")

    def _message(self):
        messages.success(self.request, "Check your email for a login link.")

    def form_valid(self, form):
        success_url = form.cleaned_data.get("success_url")
        if success_url:
            self.success_url = success_url
        else:
            # Always set message no matter what
            self._message()

        email = form.cleaned_data["email"].lower()
        after_login_url = form.cleaned_data.get("after_login_url") or self.request.GET.get("next")
        login(email, self.request, after_login_url=after_login_url, name=form.cleaned_data.get("name"))

        return super().form_valid(form)


def email_returning_user(user, url):
    send_mail(
        "Login to ✨Totem✨",
        "old_login",
        {"url": mark_safe(url)},
        recipient_list=[user.email],  # type: ignore
    )


def email_new_user(user, url):
    send_mail(
        "Welcome to ✨Totem✨",
        "new_login",
        {"url": mark_safe(url)},
        recipient_list=[user.email],  # type: ignore
    )


def login(email: str, request, after_login_url: str | None = None, mobile: bool = False, name: str | None = None):
    """Login a user by sending them a login link via email.

    Args:
        email (str): The email address to send the login link to.
        after_login_url (str, optional): The URL to redirect to after the user logs in. Defaults to None.
    """
    existing = False

    if not after_login_url or after_login_url.startswith("http"):
        after_login_url = reverse("pages:home")

    try:
        user = User.objects.get(email=email)
        existing = True
    except User.DoesNotExist:
        user = User.objects.create(email=email)
        if name:
            user.name = name  # type: ignore
            user.save()

    if mobile:
        url = "https://app.totem.org" + reverse("magic-login")
    else:
        url = request.build_absolute_uri(reverse("magic-login"))
    url += get_query_string(user)
    url += "&next=" + after_login_url
    if existing:
        email_returning_user(user, url)
    else:
        email_new_user(user, url)
    user.identify()  # type: ignore
    return user
