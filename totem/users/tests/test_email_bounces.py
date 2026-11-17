import logging
from unittest.mock import patch

import pytest
from anymail.exceptions import AnymailRecipientsRefused
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from totem.email.emails import login_pin_email, send_welcome_email, welcome_email
from totem.email.exceptions import EmailBounced
from totem.email.models import EmailLog
from totem.users.models import LoginPin, User
from totem.users.tests.factories import UserFactory
from totem.users.views import EMAIL_BOUNCED_MESSAGE

pytestmark = pytest.mark.django_db


def _bounce():
    return patch("totem.email.utils.django_send_mail", side_effect=AnymailRecipientsRefused())


def _flagged_user(**kwargs) -> User:
    return UserFactory(email_bounced_at=timezone.now(), **kwargs)


class TestRecordingABounce:
    def test_bounce_flags_the_user(self):
        user = UserFactory()
        with _bounce(), pytest.raises(EmailBounced):
            welcome_email(user).send()
        user.refresh_from_db()
        assert user.email_bounced_at is not None

    def test_bounced_login_email_also_flags_the_user(self):
        user = UserFactory()
        with _bounce(), pytest.raises(EmailBounced):
            login_pin_email(user.email, "123456").send()
        user.refresh_from_db()
        assert user.email_bounced_at is not None

    def test_welcome_email_bounce_is_not_logged_as_an_error(self, caplog: pytest.LogCaptureFixture):
        user = UserFactory()
        with _bounce(), caplog.at_level(logging.ERROR):
            send_welcome_email(user)
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


class TestSkippingFlaggedUsers:
    def test_emails_to_a_flagged_user_are_skipped(self):
        user = _flagged_user()
        welcome_email(user).send()
        assert mail.outbox == []
        assert not EmailLog.objects.exists()

    def test_login_emails_are_always_attempted(self):
        user = _flagged_user()
        login_pin_email(user.email, "123456").send()
        assert [m.to for m in mail.outbox] == [[user.email]]

    def test_mobile_pin_request_reaches_a_flagged_user(self, client: Client):
        user = _flagged_user()
        response = client.post(
            reverse("mobile-api:auth_request_pin"), data={"email": user.email}, content_type="application/json"
        )
        assert response.status_code == 200
        assert [m.to for m in mail.outbox] == [[user.email]]

    def test_mobile_pin_request_that_bounces_still_reports_invalid_email(self, client: Client):
        user = UserFactory()
        with _bounce():
            response = client.post(
                reverse("mobile-api:auth_request_pin"), data={"email": user.email}, content_type="application/json"
            )
        assert response.status_code == 401
        user.refresh_from_db()
        assert user.email_bounced_at is not None

    def test_web_login_that_bounces_shows_a_form_error(self, client: Client):
        user = UserFactory()
        with _bounce():
            response = client.post(reverse("users:login"), {"email": user.email})
        assert response.status_code == 200
        assert escape(EMAIL_BOUNCED_MESSAGE) in response.content.decode()
        user.refresh_from_db()
        assert user.email_bounced_at is not None

    def test_web_signup_that_bounces_sends_no_welcome_email(self, client: Client):
        with _bounce(), patch("totem.users.views.emails.send_welcome_email") as welcome:
            response = client.post(reverse("users:login"), {"email": "new@totem.org"})
        assert response.status_code == 200
        welcome.assert_not_called()


class TestClearingTheFlag:
    def test_changing_the_email_clears_it(self):
        user = _flagged_user()
        user.email = "new-address@example.com"
        user.save()
        user.refresh_from_db()
        assert user.email_bounced_at is None

    def test_saving_with_the_same_email_keeps_it(self):
        user = _flagged_user()
        user.name = "Someone"
        user.save()
        user.refresh_from_db()
        assert user.email_bounced_at is not None

    def test_mobile_email_change_clears_it(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        User.objects.filter(pk=user.pk).update(email_bounced_at=timezone.now())
        response = client.post(
            reverse("mobile-api:user_update"), data={"email": "moved@example.com"}, content_type="application/json"
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.email_bounced_at is None

    def test_web_profile_email_change_clears_it(self, client: Client):
        user = _flagged_user()
        client.force_login(user)
        client.post(reverse("users:profile"), {"email": "moved@example.com", "name": "Name", "timezone": "UTC"})
        user.refresh_from_db()
        assert user.email == "moved@example.com"
        assert user.email_bounced_at is None

    def test_logging_in_with_an_emailed_pin_clears_it(self):
        user = _flagged_user()
        pin = LoginPin.objects.generate_pin(user)
        assert LoginPin.objects.validate_pin(user, pin.pin) == (True, None)
        user.refresh_from_db()
        assert user.email_bounced_at is None

    def test_fixed_pin_login_keeps_it(self):
        user = _flagged_user(fixed_pin="111111", fixed_pin_enabled=True)
        assert LoginPin.objects.validate_pin(user, "111111") == (True, None)
        user.refresh_from_db()
        assert user.email_bounced_at is not None


class TestUserApiDoesNotExposeTheFlag:
    def test_current_user(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        assert "email_bounced_at" not in client.get(reverse("mobile-api:user_current")).json()
