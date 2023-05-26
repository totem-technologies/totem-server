import uuid

from django.conf import settings
from django.db import models
from django.template.loader import render_to_string
from django.urls import reverse

from totem.email.utils import send_mail

# subscribe: form, welcome email, subscribed page
# unsubscribe: unsubscribe link, unsubscribe page, unsubscribe email


class WaitList(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True, unique=True, verbose_name="Your email")  # type: ignore
    name = models.CharField(max_length=255, verbose_name="Your name")
    date_created = models.DateTimeField(auto_now_add=True)
    subscribed = models.BooleanField(default=False)

    def __str__(self):
        return str(self.id) + " - " + self.email

    def send_subscribe_email(self):
        send_mail(
            "Welcome to ✨Totem✨",
            "waitlist",
            self,
            [self.email],
        )

    @property
    def subscribe_url(self):
        return reverse("email:waitlist_subscribe", kwargs={"id": str(self.id)})

    def subscribe(self):
        self.subscribed = True
        self.save()
