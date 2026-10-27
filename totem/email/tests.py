import re
from pathlib import Path

import pytest
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from totem.email.emails import login_pin_email, missed_session_email, notify_session_advertisement, welcome_email
from totem.spaces.tests.factories import SessionFactory
from totem.users.models import LoginPin
from totem.users.tests.factories import UserFactory

from .views import get_templates


def _get_email_content(email) -> str:
    """Get decoded content from all parts of an email message."""
    msg = email.message()
    parts = []
    for part in msg.walk():
        if part.get_content_type() in ("text/plain", "text/html"):
            payload = part.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(part.get_content_charset() or "utf-8"))
    return "\n".join(parts)


class TestTemplateDevEmail:
    def test_template_view_public(self, client: Client, db):
        self._test_templates(client, status_code=404)

    @override_settings(DEBUG=True)
    def test_template_view_debug(self, client: Client, db):
        UserFactory()
        SessionFactory()
        self._test_templates(client)

    def test_template_view_staff(self, client: Client, db):
        user = UserFactory()
        user = UserFactory(is_staff=True)
        SessionFactory()
        client.force_login(user)
        self._test_templates(client)

    def _test_templates(self, _client: Client, status_code=200):
        templ_names = get_templates().keys()
        for templ_name in templ_names:
            response = _client.get(reverse("email:template", kwargs={"name": templ_name}))
            assert response.status_code == status_code

    def test_template_list_public(self, client: Client, db):
        response = client.get(reverse("email:template"))
        assert response.status_code == 404

    @override_settings(DEBUG=True)
    def test_template_list_debug(self, client: Client, db):
        response = client.get(reverse("email:template"))
        assert response.status_code == 200

    def test_template_list_staff(self, client: Client, db):
        user = UserFactory(is_staff=True)
        client.force_login(user)
        response = client.get(reverse("email:template"))
        assert response.status_code == 200


class TestDarkMode:
    def test_all_emails_support_dark_mode(self, db):
        UserFactory()
        SessionFactory()
        for name, make_email in get_templates().items():
            html = make_email().render_html()
            assert '<meta name="color-scheme" content="light dark"' in html, name
            assert "prefers-color-scheme: dark" in html, name
            # Outlook.com and Outlook mobile ignore the media query and mark dark mode with these attributes instead.
            assert "[data-ogsc]" in html, name
            assert "[data-ogsb]" in html, name
            assert "totem-logo-creme.png" in html, name

    def test_template_colors_have_dark_mode_classes(self):
        # Any color set directly in a template overrides the base styles, so it
        # needs a dm-* class from _base.mjml to pick up the dark palette.
        templates = Path(__file__).parent / "templates/email/emails"
        for path in templates.glob("[!_]*.mjml"):
            for tag in re.findall(r"<[^>]*#[0-9a-fA-F]{3,6}\b[^>]*>", path.read_text()):
                assert "dm-" in tag, f"{path.name}: {tag}"

    @pytest.mark.parametrize("mode", ["dark", "light"])
    def test_preview_mode(self, client: Client, db, mode: str):
        client.force_login(UserFactory(is_staff=True))
        response = client.get(reverse("email:template", kwargs={"name": "login_pin"}), {"mode": mode})
        assert re.search(rf'<iframe[^>]*\sstyle="[^"]*color-scheme: {mode};', response.content.decode())

    def test_preview_defaults_to_system_mode(self, client: Client, db):
        client.force_login(UserFactory(is_staff=True))
        for params in ({}, {"mode": "bogus"}):
            response = client.get(reverse("email:template", kwargs={"name": "login_pin"}), params)
            content = response.content.decode()
            assert re.search(r"<iframe", content)
            assert not re.search(r'<iframe[^>]*\sstyle="[^"]*color-scheme', content)


class TestAdvertEmail:
    def test_advert_email(self, client, db):
        user = UserFactory()
        user.save()
        event = SessionFactory()
        event.save()
        notify_session_advertisement(event, user).send()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = _get_email_content(email)
        assert "http://testserver/spaces/session" in message
        assert event.space.title in message
        assert "http://testserver/spaces/subscribe" in message
        assert event.space.slug in message

    def test_advert_email_with_content(self, client, db):
        user = UserFactory()
        user.save()
        event = SessionFactory(content="This is a test content")
        event.save()
        notify_session_advertisement(event, user).send()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = _get_email_content(email)
        assert "This is a test" in message

    def test_advert_email_with_space_content(self, client, db):
        user = UserFactory()
        user.save()
        event = SessionFactory()
        event.save()
        event.space.content = "This is a space test"
        event.space.save()
        notify_session_advertisement(event, user).send()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = _get_email_content(email)
        assert "This is a space" in message


class TestAuthEmails:
    def test_login_pin_email(self, client, db):
        user = UserFactory()
        pin = LoginPin.objects.generate_pin(user)
        login_pin_email(user.email, pin.pin).send()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = _get_email_content(email)
        assert pin.pin in message
        # Gmail only offers its "Copy code" shortcut when the email reads like a
        # verification code email: "code" in the subject, and a label in the same
        # HTML element as the PIN.
        assert "verification code" in email.subject.lower()
        html = email.alternatives[0][0]
        assert re.search(rf"Your code is:\s*<span[^>]*>\s*{pin.pin}", html)


class TestWelcomeEmail:
    def test_welcome_email(self, client, db):
        user = UserFactory()
        welcome_email(user).send()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        assert email.subject == "Welcome to Totem!"
        message = _get_email_content(email)
        assert "We're so glad you're here." in message
        assert "http://testserver/spaces/" in message
        assert "http://testserver/how-it-works/" in message
        assert "http://testserver/guidelines/" in message
        html = email.alternatives[0][0]
        assert "We pass a digital talking piece" in html


class TestMissedSessionEmail:
    def test_missed_session_email(self, client, db):
        user = UserFactory()
        user.save()
        event = SessionFactory(title="Test Event")
        event.save()
        event.attendees.add(user)
        assert len(mail.outbox) == 0
        missed_session_email(event, user).send()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = _get_email_content(email)
        assert "http://testserver/spaces/session" in message
        assert event.title in message
        assert "missed you" in message
        assert "forms.gle" in message


class TestMailerSettings:
    def test_email_backend_configured_through_mailers(self, settings):
        # Django 6.1 deprecated EMAIL_BACKEND and friends in favour of MAILERS.
        # Any settings module that still defines them trips a warning on
        # every request, so guard against them creeping back in.
        assert "default" in settings.MAILERS
        for name in ("EMAIL_BACKEND", "EMAIL_TIMEOUT", "EMAIL_HOST", "EMAIL_PORT"):
            assert not settings.is_overridden(name), f"{name} should live in MAILERS"

    def test_outbox_receives_mail(self, settings):
        from django.core import mail

        from totem.email.utils import send_mail

        send_mail("Hi", "<p>hi</p>", "hi", ["to@example.com"])
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Hi"
