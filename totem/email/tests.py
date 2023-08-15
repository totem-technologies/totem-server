import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from totem.email.models import SubscribedModel

from .utils import validate_email_blocked
from .views import signature_view

User = get_user_model()


class SubscribeTestCase(TestCase):
    fixtures = ["users.yaml"]

    def test_subscribe(self):
        user = User.objects.get(pk=1)
        subscribed = SubscribedModel.objects.create(user=user)
        assert subscribed.subscribed is False
        subscribed.subscribe()
        assert subscribed.subscribed is True
        subscribed.unsubscribe()
        assert subscribed.subscribed is False

    def test_subscribe_email(self):
        user = User.objects.get(pk=1)
        subscribed = SubscribedModel.objects.create(user=user)
        subscribed.send_subscribe_email()
        assert len(mail.outbox) == 1


def test_validate_email_blocked():
    assert validate_email_blocked("example@domain.com") is None
    assert validate_email_blocked("test@domain.com") is None
    assert validate_email_blocked("user@domain.com") is None
    with pytest.raises(ValidationError):
        validate_email_blocked("test@data-backup-store.com")


def test_signature_view():
    factory = RequestFactory()
    request = factory.get(reverse("email:signature"))
    response = signature_view(request)
    assert response.status_code == 200
    assert b"YOUR_NAME_HERE" in response.content
    assert b"YOUR_TITLE_HERE" in response.content
    assert b"YOUR_PHONE_HERE" in response.content
    assert b"YOUR_EMAIL_HERE" in response.content

    request = factory.get(
        reverse("email:signature") + "?name=John&title=Developer&phone=1234567890&email=john@example.com"
    )
    response = signature_view(request)
    assert response.status_code == 200
    assert b"John" in response.content
    assert b"Developer" in response.content
    assert b"1234567890" in response.content
    assert b"john@example.com" in response.content
