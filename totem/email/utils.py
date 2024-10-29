import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail as django_send_mail
from pydantic import BaseModel

from totem.email.data import EMAIL_BLOCKLIST

session = requests.Session()


def send_mail(
    subject: str,
    html_message: str,
    text_message: str,
    recipient_list: list[str],
    from_email: str = settings.DEFAULT_FROM_EMAIL,
    fail_silently: bool = False,
) -> int:
    # remove newlines from subject
    subject = subject.replace("\n", " ")
    return django_send_mail(
        subject, text_message, from_email, recipient_list, fail_silently=fail_silently, html_message=html_message
    )


class Recipient(BaseModel):
    email: str


class EmailData(BaseModel):
    templateId: int
    to: list[Recipient]
    replyTo: Recipient


def send_brevo_email(
    template_id: int,
    recipient: str,
    fail_silently: bool = False,
) -> int:
    api_url = "https://api.brevo.com/v3/smtp/email"
    key = settings.BREVO_API_KEY
    if not settings.SEND_BREVO_EMAILS:
        print("Not sending email because SEND_BREVO_EMAILS is False.")
        return 200
    if not key:
        raise Exception("No BREVO_API_KEY set, not sending email.")
    headers = {
        "api-key": key,
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    data = EmailData(
        templateId=template_id,
        to=[Recipient(email=recipient)],
        replyTo=Recipient(email=settings.EMAIL_SUPPORT_ADDRESS),
    )
    response = session.post(api_url, headers=headers, json=data.model_dump())
    if not fail_silently:
        response.raise_for_status()
    return response.status_code


def validate_email_blocked(value):
    for blocked in EMAIL_BLOCKLIST:
        if blocked in value:
            raise ValidationError("Sorry, but your email address is not allowed.")
