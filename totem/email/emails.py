from django.conf import settings
from django.utils.safestring import mark_safe

from .utils import send_template_mail


def send_returning_login_email(email: str, url: str):
    template_id = "neqvygmrk2wl0p7w"
    send_template_mail(
        template_id=template_id,
        recipient=email,
        subject="Sign in to Totem!",
        context={"link": mark_safe(url), "support_email": settings.EMAIL_SUPPORT_ADDRESS},
    )


def send_new_login_email(email: str, url: str):
    template_id = "351ndgwzn25gzqx8"
    send_template_mail(
        template_id=template_id,
        recipient=email,
        subject="Welcome to ✨Totem✨!",
        context={"link": mark_safe(url), "support_email": settings.EMAIL_SUPPORT_ADDRESS},
    )
