import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse

from totem.email.utils import send_mail

# subscribe: form, welcome email, subscribed page
# unsubscribe: unsubscribe link, unsubscribe page, unsubscribe email


class SubscribedModel(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscribed",
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscribed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def send_subscribe_email(self):
        send_mail(
            "Welcome to ✨Totem✨",
            "subscribe",
            self,
            [self.user.email],
        )

    def send_welcome_email(self):
        send_mail(
            "Welcome to ✨Totem✨",
            "welcome",
            self,
            [self.user.email],
        )

    def subscribe(self):
        self.subscribed = True
        self.save()

    def unsubscribe(self):
        self.subscribed = False
        self.save()

    @property
    def subscribe_url(self):
        return reverse("email:subscribe", kwargs={"id": str(self.id)})

    @property
    def unsubscribe_url(self):
        return reverse("email:unsubscribe", kwargs={"id": str(self.id)})
