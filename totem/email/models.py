import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

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
        raise NotImplementedError

    def send_welcome_email(self):
        raise NotImplementedError

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


class EmailLog(models.Model):
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    template = models.CharField(max_length=255)
    context = models.JSONField(null=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.recipient} - {self.subject} ({self.created})"

    @classmethod
    def clear_old(cls):
        cls.objects.filter(created__lte=timezone.now() - timedelta(days=30)).delete()

    class Meta:
        verbose_name_plural = "Email Logs"
        ordering = ("-created",)
