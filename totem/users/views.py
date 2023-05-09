from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, RedirectView, UpdateView, FormView
from .forms import LoginForm
from django.urls import reverse_lazy
from sesame.utils import get_query_string
from django.core.mail import send_mail
from django.contrib import messages


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
        return self.request.user.get_absolute_url()

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
        email = form.cleaned_data["email"].lower()
        # Always set messsage no matter what
        self._message()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return super().form_valid(form)
        next_url = reverse("pages:home")
        url = self.request.build_absolute_uri(reverse("magic-login")) + get_query_string(user) + "&next=" + next_url
        send_mail(
            "Log in to Totem",
            "Welcome back! Click here to log in: " + url,
            "noreply@totem.org",
            fail_silently=False,
            recipient_list=[user.email],  # type: ignore
        )

        return super().form_valid(form)
