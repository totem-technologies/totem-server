from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from totem.email.models import SubscribedModel

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
