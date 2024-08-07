from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from totem.circles.tests.factories import CircleEventFactory
from totem.email.emails import send_notify_circle_advertisement, send_returning_login_email
from totem.users.tests.factories import UserFactory

from .views import get_templates


class TestTemplateDevEmail:
    def test_template_view_public(self, client: Client):
        self._test_templates(client, status_code=404)

    @override_settings(DEBUG=True)
    def test_template_view_debug(self, client: Client):
        self._test_templates(client)

    def test_template_view_staff(self, client: Client, db):
        user = UserFactory(is_staff=True)
        client.force_login(user)
        self._test_templates(client)

    def _test_templates(self, _client: Client, status_code=200):
        templ_names = get_templates().keys()
        for templ_name in templ_names:
            response = _client.get(reverse("email:template", kwargs={"name": templ_name}))
            assert response.status_code == status_code

    def test_template_list_public(self, client: Client):
        response = client.get(reverse("email:template"))
        assert response.status_code == 404

    @override_settings(DEBUG=True)
    def test_template_list_debug(self, client: Client):
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
        event = CircleEventFactory()
        event.save()
        send_notify_circle_advertisement(event, user)
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/circles/event" in message
        assert event.circle.title in message
        assert "http://testserver/circles/subscribe" in message
        assert event.circle.slug in message


class TestReturningUsers:
    def test_returning_users(self, client, db):
        user = UserFactory()
        user.save()
        send_returning_login_email(user.email, reverse("pages:home"))
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/" in message

    def test_returning_users_after_login(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        send_returning_login_email(user.email, reverse("pages:home"))
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/" in message
