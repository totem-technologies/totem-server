import uuid
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from totem.utils.models import BaseModel

MAX_ACTIVITY_PAGES = 100

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
        cls.objects.filter(created__lte=timezone.now() - timedelta(days=365)).delete()

    class Meta:
        verbose_name_plural = "Email Logs"
        ordering = ("-created",)


class EmailActivity(BaseModel):
    id = models.AutoField(primary_key=True)  # Internal primary key
    activity_id = models.CharField(max_length=255, unique=True)  # MailerSend's activity ID
    event_type = models.CharField(max_length=50, null=True)
    email = models.EmailField(blank=True, null=True)
    timestamp = models.DateTimeField()
    subject = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.event_type} - {self.timestamp}"

    @classmethod
    def fetch_email_activity(cls):
        try:
            # If the newest log is less than 12 hours old, don't fetch new logs
            if cls.objects.latest("timestamp").timestamp > timezone.now() - timedelta(hours=12):
                print("Skipping fetch_email_activity because the newest log is less than 12 hours old.")
                return
        except cls.DoesNotExist:
            pass
        _fetch_email_activity()

    @classmethod
    def clear_old(cls):
        cls.objects.filter(date_created__lte=timezone.now() - timedelta(days=30)).delete()


def _fetch_email_activity():
    if not settings.MAILERSEND_COLLECT_ACTIVITY:
        return
    if not settings.MAILERSEND_API_TOKEN:
        raise Exception("MAILERSEND_API_TOKEN not set")
    if not settings.MAILERSEND_DOMAIN_ID:
        raise Exception("MAILERSEND_DOMAIN_ID not set")
    page = 1
    now = timezone.now()
    while True:
        next = _get_activity_page(page, now)
        if not next or page > MAX_ACTIVITY_PAGES:
            break
        page += 1


def _get_activity_page(page: int, now: datetime):
    DOMAIN_ID = settings.MAILERSEND_DOMAIN_ID
    MAILERSEND_API_URL = f"https://api.mailersend.com/v1/activity/{DOMAIN_ID}"

    # Convert datetime to Unix timestamps
    date_from = int((now - timedelta(days=1)).timestamp())
    date_to = int(now.timestamp())

    params = {
        "date_from": date_from,  # Unix timestamp
        "date_to": date_to,  # Unix timestamp
        "limit": 100,
        "page": page,
    }

    headers = {"Authorization": f"Bearer {settings.MAILERSEND_API_TOKEN}"}

    try:
        response = requests.get(MAILERSEND_API_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch email activity: {e}")
        return False

    payload = response.json()
    next = payload.get("links", {}).get("next")
    activities = payload.get("data", [])
    for activity in activities:
        _save_activity(activity)
    return next is not None


def _save_activity(activity: dict):
    _ = EmailActivity.objects.update_or_create(
        activity_id=activity["id"],
        defaults={
            "event_type": activity["type"],
            "timestamp": datetime.fromisoformat(activity["updated_at"]),
            "email": activity.get("email", {}).get("recipient", {}).get("email"),
            "status": activity.get("email", {}).get("status"),
            "subject": activity.get("email", {}).get("subject"),
            "data": activity,
        },
    )
