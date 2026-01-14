from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse

if TYPE_CHECKING:
    from totem.spaces.models import Session
    from totem.users.models import User

import mrml
from django.template.loader import render_to_string
from pydantic import AnyHttpUrl, BaseModel, TypeAdapter

from .models import EmailLog
from .utils import send_brevo_email, send_mail


def type_url(url: str):
    return TypeAdapter(AnyHttpUrl).validate_python(url)


def _make_email_url(link) -> AnyHttpUrl:
    return type_url(urllib.parse.urljoin(settings.SITE_BASE_URL, link))


def _to_human_time(user: User, dt: datetime):
    # 06:56 PM EDT on Friday, August 25
    return dt.astimezone(user.timezone).strftime("%I:%M %p %Z on %A, %B %d")


class Email(BaseModel):
    template: str
    subject: str
    recipient: str
    support_email: str = settings.EMAIL_SUPPORT_ADDRESS
    show_env_banner: bool = settings.EMAIL_SHOW_ENV_BANNER
    environment: str = settings.ENVIRONMENT_NAME

    def render_html(self) -> str:
        s = render_to_string(f"email/emails/{self.template}.mjml", context=self.model_dump())
        return mrml.to_html(s).content

    def render_text(self) -> str:
        return render_to_string(f"email/emails/{self.template}.txt", context=self.model_dump())

    def send(self):
        # if blocking:
        send_mail(
            subject=self.subject,
            html_message=self.render_html(),
            text_message=self.render_text(),
            recipient_list=[self.recipient],
        )
        # else:
        #     global_pool.add_task(
        #         send_mail,
        #         subject=self.subject,
        #         html_message=self.render_html(),
        #         text_message=self.render_text(),
        #         recipient_list=[self.recipient],
        #     )
        EmailLog.objects.create(
            subject=self.subject,
            template=self.template,
            context=self.model_dump(mode="json"),
            recipient=self.recipient,
        )


class BrevoEmail(BaseModel):
    template_id: int
    recipient: str
    show_env_banner: bool = settings.EMAIL_SHOW_ENV_BANNER
    environment: str = settings.ENVIRONMENT_NAME

    def send(self):
        send_brevo_email(
            template_id=self.template_id,
            recipient=self.recipient,
        )


class WelcomeEmail(BrevoEmail):
    template_id: int = 3


class ButtonEmail(Email):
    template: str = "button"
    button_text: str
    link: AnyHttpUrl
    title: str
    message: str


class LoginPinEmail(Email):
    template: str = "pin"
    subject: str = "Your Totem login PIN"
    title: str = "Here's your login PIN"
    message: str = "Use this 6-digit PIN to sign in. It expires in 15 minutes and can only be used once."
    pin: str


class SessionStartingEmail(Email):
    template: str = "circle_starting"
    start: str
    event_title: str
    event_link: AnyHttpUrl
    link: AnyHttpUrl
    button_text: str = "Join Session"
    subject: str = "🚨 Space is starting soon 🚨"
    title: str = "Get Ready!"


class SessionAdvertisementEmail(Email):
    template: str = "circle_ad"
    start: str
    event_title: str
    space_title: str
    space_subtitle: str
    author: str
    unsubscribe_url: AnyHttpUrl
    link: AnyHttpUrl
    button_text: str = "Reserve a spot"
    subject: str = "New Session"
    event_details: str | None
    title: str
    subtitle: str
    image_url: str | None
    author_image_url: str | None


class SessionTomorrowReminderEmail(Email):
    template: str = "circle_tomorrow_reminder"
    start: str
    event_title: str
    link: AnyHttpUrl
    button_text: str = "Add to calendar"
    subject: str = "You have a session coming up tomorrow"
    title: str = "Space Tomorrow"


class SessionSignupEmail(Email):
    template: str = "circle_signup"
    start: str
    event_title: str
    link: AnyHttpUrl
    button_text: str = "Add to calendar"
    subject: str = "Your spot is saved"
    title: str = "Spot Saved"


class TestEmail(Email):
    template: str = "test"
    start: str
    event_title: str
    link: AnyHttpUrl
    button_text: str = "Add to calendar"
    subject: str = "Your spot is saved"
    title: str = "Spot Saved"


class MissedSessionEmail(Email):
    template: str = "missed_event"
    start: str
    event_title: str
    link: AnyHttpUrl = type_url("https://forms.gle/qnEKej6Pt4JAZTH79")
    event_link: AnyHttpUrl
    button_text: str = "Let us know how we can help"
    subject: str = "We missed you!"
    title: str = "We missed you!"


def login_pin_email(email: str, pin: str) -> Email:
    if settings.DEBUG:
        print("------------------------------------------")
        print(f"Sending PIN email to {email} with PIN: {pin}")
        print("------------------------------------------")
    return LoginPinEmail(
        recipient=email,
        pin=pin,
    )


def welcome_email(user: User) -> BrevoEmail:
    if settings.DEBUG:
        print("------------------------------------------")
        print(f"Sending welcome email to {user.email}")
        print("------------------------------------------")
    return WelcomeEmail(recipient=user.email)


def notify_session_starting(event: Session, user: User) -> Email:
    start = _to_human_time(user, event.start)
    return SessionStartingEmail(
        recipient=user.email,
        start=start,
        event_title=event.space.title,
        event_link=_make_email_url(event.get_absolute_url()),
        link=type_url(event.email_join_url(user)),
    )


def notify_session_tomorrow(event: Session, user: User) -> Email:
    start = _to_human_time(user, event.start)
    title = event.title or event.space.title or event.space.title
    return SessionTomorrowReminderEmail(
        title=f"Tomorrow - {title}",
        subject=f"Tomorrow - {title}",
        recipient=user.email,
        start=start,
        event_title=event.space.title,
        link=_make_email_url(event.get_absolute_url()),
    )


def notify_session_advertisement(event: Session, user: User) -> Email:
    start = _to_human_time(user, event.start)
    title = event.title or event.space.subtitle
    subtitle = event.space.title
    details = None
    if event.content:
        details = event.content_html
    elif event.space.content:
        details = event.space.content_html
    image_url = event.space.image.url if event.space.image else None
    author_image_url = event.space.author.profile_image.url if event.space.author.profile_image else None
    subject = f"✨New: {title}✨"
    return SessionAdvertisementEmail(
        recipient=user.email,
        link=_make_email_url(event.get_absolute_url()),
        subject=subject,
        start=start,
        event_title=event.title,
        space_title=event.space.title,
        space_subtitle=event.space.subtitle,
        event_details=details,
        title=title,
        subtitle=subtitle,
        author=event.space.author.name,
        image_url=image_url,
        author_image_url=author_image_url,
        unsubscribe_url=type_url(event.space.subscribe_url(user, subscribe=False)),
    )


def notify_session_signup(event: Session, user: User) -> Email:
    start = _to_human_time(user, event.start)
    return SessionSignupEmail(
        recipient=user.email,
        link=_make_email_url(reverse("spaces:calendar", kwargs={"event_slug": event.slug})),
        start=start,
        event_title=event.space.title,
    )


def missed_session_email(event: Session, user: User) -> Email:
    start = _to_human_time(user, event.start)
    title = event.title or event.space.title
    return MissedSessionEmail(
        recipient=user.email,
        start=start,
        event_title=title,
        event_link=_make_email_url(event.get_absolute_url()),
    )


notify_circle_starting = notify_session_starting
notify_circle_tomorrow = notify_session_tomorrow
notify_circle_advertisement = notify_session_advertisement
notify_circle_signup = notify_session_signup
missed_event_email = missed_session_email
