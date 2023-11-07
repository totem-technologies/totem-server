from pathlib import Path
from typing import Any

from anymail.message import AnymailMessage
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail as django_send_mail
from django.template.loader import render_to_string
from mjml import mjml2html

from totem.email.data import EMAIL_BLOCKLIST


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


def send_mjml_mail(
    subject: str,
    template: str,
    context: Any,
    recipient_list: list[str],
    from_email: str = settings.DEFAULT_FROM_EMAIL,
    fail_silently: bool = False,
) -> int:
    html_message = render_email(template, context)
    text_message = render_to_string(f"email/emails/{template}.txt", context)
    return django_send_mail(
        subject, text_message, from_email, recipient_list, fail_silently=fail_silently, html_message=html_message
    )


def send_template_mail(
    *,
    template_id: str,
    recipient: str,
    subject: str,
    context: dict[str, str],
    from_email: str = settings.DEFAULT_FROM_EMAIL,
    fail_silently: bool = False,
) -> int:
    if settings.DEBUG:
        print(f"Sending email to {recipient} with template {template_id}")
        print(f"Context: {context}")
    message = AnymailMessage(
        subject=subject,  # use the subject in our stored template
        from_email=from_email,
        to=[recipient],
    )
    message.template_id = template_id  # use this ESP stored template
    message.merge_global_data = context  # per-recipient data to merge into the template
    return message.send(fail_silently=fail_silently)


def validate_email_blocked(value):
    for blocked in EMAIL_BLOCKLIST:
        if blocked in value:
            raise ValidationError("Sorry, but your email address is not allowed.")


def render_email(template: str, context: dict[str, Any]) -> str:
    return mjml2html(render_to_string(f"email/emails/{template}.mjml", context=context))


def get_templates():
    files = Path(__file__).parent.joinpath("templates/email/emails").glob("*.mjml")
    return {file.stem: file.name for file in files}
