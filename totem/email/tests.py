from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from totem.circles.tests.factories import SessionFactory
from totem.email.emails import login_pin_email, missed_session_email, notify_session_advertisement
from totem.users.models import LoginPin
from totem.users.tests.factories import UserFactory

from .views import get_templates


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
        message = str(email.message())
        assert "http://testserver/spaces/event" in message
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
        message = str(email.message())
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
        message = str(email.message())
        assert "This is a space" in message


class TestAuthEmails:
    def test_login_pin_email(self, client, db):
        user = UserFactory()
        pin = LoginPin.objects.generate_pin(user)
        login_pin_email(user.email, pin.pin).send()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert pin.pin in message
        assert "PIN" in message


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
        message = str(email.message())
        assert "http://testserver/spaces/event" in message
        assert event.title in message
        assert "missed you" in message
        assert "forms.gle" in message
