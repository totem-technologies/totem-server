from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse
from django.utils.safestring import SafeString

if TYPE_CHECKING:
    from totem.circles.models import CircleEvent
    from totem.users.models import User

from pydantic import BaseModel, HttpUrl

from .email_templates import ButtonEmailTemplate, EmailTemplate
from .utils import send_mail


class Email(BaseModel):
    recipient: str

    def get_template(self) -> EmailTemplate:
        raise NotImplementedError


class LoginEmail(Email):
    url: HttpUrl
    button_text: str = "Sign in"
    subject: str = "Totem sign in link"
    title: str = "Sign in link"
    message: str = "You requested a link to sign in, and here it is! Note that this link expires in an hour and can only be used once."

    def get_template(self):
        return ButtonEmailTemplate(
            button_text=self.button_text,
            link=self.url,
            title=self.title,
            subject=self.subject,
            message=self.message,
        )


class ChangeEmailEmail(Email):
    old_email: str
    new_email: str
    login_url: HttpUrl
    button_text: str = "Confirm"
    subject: str = "Confirm your new email address"
    title: str = "Confirm your new email address"
    message: str = "You're almost there! Please confirm your new email address by clicking the button below."

    def get_template(self):
        return ButtonEmailTemplate(
            button_text=self.button_text,
            link=self.login_url,
            title=self.title,
            subject=self.subject,
            message=self.message,
        )


class CircleStartingEmail(Email):
    start: str
    event_title: str
    link: HttpUrl
    button_text: str = "Join Circle"
    subject: str = "Your Circle is starting soon"
    title: str = "Get Ready"
    message: str = "Your Circle, {event_title}, is starting at {start}. \
            Click the button below to join the Circle. If you are more than 5 minutes late, you may not be allowed to participate."

    def get_template(self):
        formatted_message = self.message.format(event_title=self.event_title, start=self.start)
        return ButtonEmailTemplate(
            button_text=self.button_text,
            link=self.link,
            title=self.title,
            subject=self.subject,
            message=formatted_message,
        )


class CircleAdvertisementEmail(Email):
    start: str
    event_title: str
    unsubscribe_url: HttpUrl
    link: HttpUrl
    button_text: str = "Reserve a spot"
    subject: str = "Join an upcoming Circle"
    title: str = "New Circle"
    message: str = 'A session for a Circle you are subscribed to, "{event_title}", is coming up at {start}. \
            Click the button below to reserve a spot before this one fills up. If you no longer wish to get notifications about this Circle, \
                you can unsubscribe here: {unsubscribe_url}'

    def get_template(self):
        formatted_message = self.message.format(
            event_title=self.event_title, start=self.start, unsubscribe_url=self.unsubscribe_url
        )
        return ButtonEmailTemplate(
            button_text=self.button_text,
            link=self.link,
            title=self.title,
            subject=self.subject,
            message=formatted_message,
        )


def send_returning_login_email(email: str, url: str):
    _url = make_email_url(url)
    send_template_email(
        LoginEmail(
            recipient=email,
            url=_url,  # type: ignore
        )
    )

    if settings.DEBUG:
        print("------------------------------------------")
        print(f"Sending email to {email} with link\n{_url}")
        print("------------------------------------------")


def send_change_email(old_email: str, new_email: str, login_url: str):
    send_template_email(
        ChangeEmailEmail(
            recipient=new_email,
            old_email=old_email,
            new_email=new_email,
            login_url=make_email_url(login_url),  # type: ignore
        )
    )


def send_notify_circle_starting(event: CircleEvent, user: User):
    start = to_user_timezone(user, event.start)
    send_template_email(
        CircleStartingEmail(
            recipient=user.email,
            start=start,
            event_title=event.circle.title,
            link=make_email_url(event.get_absolute_url()),  # type: ignore
        )
    )


def send_notify_circle_advertisement(event: CircleEvent, user: User):
    start = to_user_timezone(user, event.start)
    unsubscribe_url = make_email_url(reverse("circles:subscribe", kwargs={"slug": event.circle.slug}))
    unsubscribe_url += f"?user={user.slug}&token={event.circle.subscribe_token(user)}&action=unsubscribe"
    send_template_email(
        CircleAdvertisementEmail(
            recipient=user.email,
            link=make_email_url(event.get_absolute_url()),  # type: ignore
            start=start,
            event_title=event.circle.title,
            unsubscribe_url=unsubscribe_url,  # type: ignore
        )
    )


def to_user_timezone(user: User, dt: datetime):
    # 06:56 PM EDT on Friday, August 25
    return dt.astimezone(user.timezone).strftime("%I:%M %p %Z on %A, %B %d")


def make_email_url(link) -> SafeString:
    return SafeString(urllib.parse.urljoin(settings.EMAIL_BASE_URL, link))


def send_template_email(email: Email):
    tpl = email.get_template()
    send_mail(
        subject=tpl.subject,
        html_message=tpl.render_html(),
        text_message=tpl.render_text(),
        recipient_list=[email.recipient],
    )
