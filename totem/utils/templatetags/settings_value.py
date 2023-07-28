from django import template
from django.conf import settings

register = template.Library()

allow_list = ["ENVIRONMENT_NAME", "ENVIRONMENT_COLOR", "EMAIL_SUPPORT_ADDRESS"]


@register.simple_tag
def settings_value(name):
    if name in allow_list:
        return getattr(settings, name, "")
    return ""
