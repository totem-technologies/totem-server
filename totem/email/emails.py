from django.conf import settings

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


def _send_button_email(*, recipient: str, subject: str, message: str, button_text: str, link: str):
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
