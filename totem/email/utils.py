from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail as django_send_mail

from totem.email.data import EMAIL_BLOCKLIST


def send_mail(
    subject: str,
    html_message: str,
    text_message: str,
    recipient_list: list[str],
    from_email: str = settings.DEFAULT_FROM_EMAIL,
    fail_silently: bool = False,
) -> int:
    return django_send_mail(
        subject, text_message, from_email, recipient_list, fail_silently=fail_silently, html_message=html_message
    )


def validate_email_blocked(value):
    for blocked in EMAIL_BLOCKLIST:
        if blocked in value:
            raise ValidationError("Sorry, but your email address is not allowed.")
