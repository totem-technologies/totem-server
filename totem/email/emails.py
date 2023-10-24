from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse

if TYPE_CHECKING:
    from totem.circles.models import CircleEvent
    from totem.users.models import User

from .utils import send_template_mail


def send_returning_login_email(email: str, url: str):
    _send_button_email(
        recipient=email,
        subject="Sign in to Totem!",
        message="It's great to see you again, welcome back. Use the magic link button below \
            to access your account. If this wasn't you, please ignore this email.",
        button_text="Sign in",
        link=url,
    )


def send_new_login_email(email: str, url: str):
    _send_button_email(
        recipient=email,
        subject="Welcome to ✨Totem✨!",
        message="We're excited to have you join us. However, we won't be able to reach you until you \
            confirm your email address. Please confirm by clicking the button below. If this wasn't you, \
                please ignore this email.",
        button_text="Confirm",
        link=url,
    )


def send_change_email(old_email: str, new_email: str, login_url: str):
    _send_button_email(
        recipient=new_email,
        subject="Confirm your new email address",
        message="You're almost there! Please confirm your new email address by clicking the button \
            below. If this wasn't you, please ignore this email.",
        button_text="Confirm",
        link=login_url,
    )


def send_notify_circle_starting(event: CircleEvent, user: User):
    # 06:56 PM EDT on Friday, August 25
    start = event.start.astimezone(user.timezone).strftime("%I:%M %p %Z on %A, %B %d")
    _send_button_email(
        recipient=user.email,
        subject="Your Circle is starting soon!",
        message=f"Your Circle, {event.circle.title}, is starting at {start}. \
            Click the button below to join the Circle. If you are more than 5 minutes late, you may not be allowed to participate.",
        button_text="Join Circle",
        link=event.get_absolute_url(),
    )


def send_notify_circle_advertisement(event: CircleEvent, user: User):
    # 06:56 PM EDT on Friday, August 25
    start = event.start.astimezone(user.timezone).strftime("%I:%M %p %Z on %A, %B %d")
    unsubscribe_url = make_email_url(reverse("circles:subscribe", kwargs={"slug": event.circle.slug}))
    unsubscribe_url += f"?user={user.slug}&token={event.circle.subscribe_token(user)}&action=unsubscribe"
    _send_button_email(
        recipient=user.email,
        subject="Join an upcoming Circle!",
        message=f'A session for a Circle you are subscribed to, "{event.circle.title}", is coming up at {start}. \
            Click the button below to reserve a spot before this one fills up. If you no longer wish to get notifications about this Circle, \
                you can unsubscribe here: {unsubscribe_url}',
        button_text="Reserve a spot",
        link=event.get_absolute_url(),
    )


def _send_button_email(*, recipient: str, subject: str, message: str, button_text: str, link: str):
    link = make_email_url(link)
    send_template_mail(
        template_id="vywj2lpv631l7oqz",
        recipient=recipient,
        subject=subject,
        context={
            "subject": subject,
            "message": message,
            "button_text": button_text,
            "link": link,
            "support_email": settings.EMAIL_SUPPORT_ADDRESS,
        },
    )


def make_email_url(link):
    return urllib.parse.urljoin(settings.EMAIL_BASE_URL, link)
