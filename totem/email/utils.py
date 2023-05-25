from typing import Any, List

from django.conf import settings
from django.core.mail import send_mail as django_send_mail
from django.template.loader import render_to_string


def send_mail(
    subject: str,
    template: str,
    context: Any,
    recipient_list: list[str],
    from_email: str = settings.DEFAULT_FROM_EMAIL,
    fail_silently: bool = False,
) -> int:
    ctx = {"ctx": context, "email_base_url": settings.EMAIL_BASE_URL}
    html_message = render_to_string(f"email/emails/{template}.html", ctx)
    text_message = render_to_string(f"email/emails/{template}.txt", ctx)
    return django_send_mail(
        subject, text_message, from_email, recipient_list, fail_silently=fail_silently, html_message=html_message
    )
