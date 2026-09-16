import pytest
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.core import mail
from django.urls import reverse

from totem.users.adapters import SocialAccountAdapter
from totem.users.forms import UserSocialSignupForm
from totem.users.models import LoginPin, User


@pytest.fixture(params=["web", "api"])
def submit_email(request, client):
    def submit(email):
        if request.param == "api":
            return client.post(
                reverse("mobile-api:auth_request_pin"),
                {"email": email},
                content_type="application/json",
            )
        return client.post(reverse("users:login"), {"email": email})

    return submit


@pytest.mark.django_db
class TestStagingSignup:
    @pytest.fixture(autouse=True)
    def staging(self, settings):
        settings.SITE_HOST = "totem.kbl.io"

    @pytest.mark.parametrize("email", ["new@example.com", "new@sub.totem.org", "new@totem.org.example.com"])
    def test_rejects_external_signup(self, submit_email, email):
        response = submit_email(email)

        assert response.status_code in (200, 403)
        assert "Please go to https://totem.org to create your account." in response.content.decode()
        assert not User.objects.exists()
        assert not LoginPin.objects.exists()
        assert len(mail.outbox) == 0

    def test_allows_totem_signup(self, submit_email):
        response = submit_email("New+staging@TOTEM.ORG")

        assert response.status_code in (200, 302)
        user = User.objects.get(email="new+staging@totem.org")
        assert LoginPin.objects.filter(user=user).exists()
        assert len(mail.outbox) == 1

    def test_allows_existing_external_account(self, submit_email):
        user = User.objects.create_user(email="existing@example.com")
        response = submit_email("EXISTING@EXAMPLE.COM")

        assert response.status_code in (200, 302)
        assert User.objects.count() == 1
        assert LoginPin.objects.filter(user=user).exists()
        assert len(mail.outbox) == 1

    @pytest.mark.parametrize("host", ["totem.org", "localhost:8000"])
    def test_allows_external_signup_elsewhere(self, settings, submit_email, host):
        settings.SITE_HOST = host
        response = submit_email("new@example.com")

        assert response.status_code in (200, 302)
        assert User.objects.filter(email="new@example.com").exists()
        assert len(mail.outbox) == 1

    def test_allauth_signup_rejects_external_email(self, client):
        response = client.post(
            reverse("account_signup"),
            {"email": "new@example.com", "password1": "long-test-password", "password2": "long-test-password"},
        )

        assert response.status_code == 200
        assert "Please go to https://totem.org to create your account." in response.content.decode()
        assert not User.objects.exists()
        assert len(mail.outbox) == 0

    def test_social_signup_rejects_external_email(self, rf):
        sociallogin = SocialLogin(
            user=User(email="new@example.com"),
            account=SocialAccount(provider="google", uid="staging-test"),
        )
        request = rf.get("/accounts/social/signup/")

        assert not SocialAccountAdapter().is_auto_signup_allowed(request, sociallogin)
        form = UserSocialSignupForm(data={"email": "new@example.com"}, sociallogin=sociallogin)
        assert not form.is_valid()
        assert "Please go to https://totem.org to create your account." in form.errors["email"][0]
        assert not User.objects.exists()

    def test_social_signup_allows_totem_email(self, rf):
        sociallogin = SocialLogin(
            user=User(email="new@TOTEM.ORG"),
            account=SocialAccount(provider="google", uid="staging-test"),
        )
        request = rf.get("/accounts/social/signup/")

        assert SocialAccountAdapter().is_auto_signup_allowed(request, sociallogin)
        form = UserSocialSignupForm(data={"email": "new@TOTEM.ORG"}, sociallogin=sociallogin)
        assert form.is_valid(), form.errors
