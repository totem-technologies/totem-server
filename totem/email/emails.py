from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse

if TYPE_CHECKING:
    from totem.circles.models import CircleEvent
    from totem.users.models import User

from django.template.loader import render_to_string
from mjml import mjml2html
from pydantic import AnyHttpUrl, BaseModel

from totem.utils.pool import global_pool

from .models import EmailLog
from .utils import send_mail


class Email(BaseModel):
    template: str
    subject: str
    recipient: str
    support_email: str = settings.EMAIL_SUPPORT_ADDRESS
    show_env_banner: bool = settings.EMAIL_SHOW_ENV_BANNER
    environment: str = settings.ENVIRONMENT_NAME

    def render_html(self) -> str:
        s = render_to_string(f"email/emails/{self.template}.mjml", context=self.model_dump())
        return mjml2html(s)

    def render_text(self) -> str:
        return render_to_string(f"email/emails/{self.template}.txt", context=self.model_dump())

    def send(self, blocking: bool = True):
        if blocking:
            send_mail(
                subject=self.subject,
                html_message=self.render_html(),
                text_message=self.render_text(),
                recipient_list=[self.recipient],
            )
        else:
            global_pool.add_task(
                send_mail,
                subject=self.subject,
                html_message=self.render_html(),
                text_message=self.render_text(),
                recipient_list=[self.recipient],
            )
        EmailLog.objects.create(
            subject=self.subject,
            template=self.template,
            context=self.model_dump(mode="json"),
            recipient=self.recipient,
        )


class ButtonEmail(Email):
    template: str = "button"
    button_text: str
    link: AnyHttpUrl
    title: str
    message: str


class LoginEmail(ButtonEmail):
    button_text: str = "Sign in"
    subject: str = "Totem sign in link"
    title: str = "Sign in link"
    message: str = "You requested a link to sign in, and here it is! Note that this link expires in an hour and can only be used once."


class ChangeEmailEmail(ButtonEmail):
    link: AnyHttpUrl
    button_text: str = "Confirm"
    subject: str = "Confirm your new email address"
    title: str = "Confirm your new email address"
    message: str = "You're almost there! Please confirm your new email address by clicking the button below."


class CircleStartingEmail(Email):
    template: str = "circle_starting"
    start: str
    event_title: str
    event_link: AnyHttpUrl
    link: AnyHttpUrl
    button_text: str = "Join Circle"
    subject: str = "Your Circle is starting soon"
    title: str = "Get Ready"


class CircleAdvertisementEmail(Email):
    template: str = "circle_ad"
    start: str
    event_title: str
    unsubscribe_url: AnyHttpUrl
    link: AnyHttpUrl
    button_text: str = "Reserve a spot"
    subject: str = "Join an upcoming Circle"
    title: str = "New Circle"


class CircleTomorrowReminderEmail(Email):
    template: str = "circle_tomorrow_reminder"
    start: str
    event_title: str
    link: AnyHttpUrl
    button_text: str = "Add to calendar"
    subject: str = "You have a Circle coming up tomorrow"
    title: str = "Circle Tomorrow"


class CircleSignupEmail(Email):
    template: str = "circle_signup"
    start: str
    event_title: str
    iso_start: str
    link: AnyHttpUrl
    button_text: str = "Add to calendar"
    subject: str = "Your spot is saved"
    title: str = "Spot Saved"


def send_returning_login_email(email: str, url: str):
    _url = make_email_url(url)
    LoginEmail(
        recipient=email,
        link=_url,  # type: ignore
    ).send()

    if settings.DEBUG:
        print("------------------------------------------")
        print(f"Sending email to {email} with link\n{_url}")
        print("------------------------------------------")


def send_change_email(old_email: str, new_email: str, login_url: str):
    ChangeEmailEmail(
        recipient=new_email,
        link=make_email_url(login_url),
    ).send()


def send_notify_circle_starting(event: CircleEvent, user: User):
    start = to_human_time(user, event.start)
    CircleStartingEmail(
        recipient=user.email,
        start=start,
        event_title=event.circle.title,
        event_link=make_email_url(event.get_absolute_url()),
        link=event.join_url(user),  # type: ignore
    ).send()


def send_notify_circle_tomorrow(event: CircleEvent, user: User):
    start = to_human_time(user, event.start)
    CircleTomorrowReminderEmail(
        recipient=user.email,
        start=start,
        event_title=event.circle.title,
        link=make_email_url(event.get_absolute_url()),
    ).send()


def send_notify_circle_advertisement(event: CircleEvent, user: User):
    start = to_human_time(user, event.start)
    CircleAdvertisementEmail(
        recipient=user.email,
        link=make_email_url(event.get_absolute_url()),
        start=start,
        event_title=event.circle.title,
        unsubscribe_url=event.circle.subscribe_url(user, subscribe=False),  # type: ignore
    ).send()


def send_notify_circle_signup(event: CircleEvent, user: User):
    start = to_human_time(user, event.start)
    CircleSignupEmail(
        recipient=user.email,
        link=make_email_url(reverse("circles:calendar", kwargs={"event_slug": event.slug})),  # type: ignore
        start=start,
        iso_start=event.start.astimezone(user.timezone).isoformat(),
        event_title=event.circle.title,
    ).send(blocking=False)


def to_human_time(user: User, dt: datetime):
    # 06:56 PM EDT on Friday, August 25
    return dt.astimezone(user.timezone).strftime("%I:%M %p %Z on %A, %B %d")


def make_email_url(link) -> AnyHttpUrl:
    return urllib.parse.urljoin(settings.SITE_BASE_URL, link)
