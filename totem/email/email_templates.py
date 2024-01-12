from django.conf import settings
from pydantic import BaseModel, HttpUrl

from .utils import render_html, render_text


class EmailTemplate(BaseModel):
    template: str
    subject: str
    support_email: str = settings.EMAIL_SUPPORT_ADDRESS
    show_env_banner: bool = settings.EMAIL_SHOW_ENV_BANNER
    environment: str = settings.ENVIRONMENT_NAME

    def render_html(self) -> str:
        return render_html(self.template, self.model_dump())

    def render_text(self) -> str:
        return render_text(self.template, self.model_dump())


class ButtonEmailTemplate(EmailTemplate):
    template: str = "button"
    button_text: str
    link: HttpUrl
    title: str
    message: str
