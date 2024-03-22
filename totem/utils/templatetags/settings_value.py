from django import template
from django.conf import settings

register = template.Library()

allow_list = [
    "ENVIRONMENT_NAME",
    "ENVIRONMENT_COLOR",
    "EMAIL_SUPPORT_ADDRESS",
    "SENTRY_ENVIRONMENT",
    "SOCIAL_LINKS",
    "SITE_BASE_URL",
]


def _value_getter(name):
    """Get the value of a setting by name, allow using dot notation for nested dict settings."""
    value = settings
    for key in name.split("."):
        if isinstance(value, dict):
            value = value.get(key, None)
        else:
            value = getattr(value, key, None)
        if value is None:
            break
    if not value:
        raise ValueError(f"Invalid setting: {name}.")
    return value


@register.simple_tag
def settings_value(name):
    if name.split(".")[0] in allow_list:
        return _value_getter(name)
    raise ValueError(f"Invalid setting: {name}. Allowed settings are: {', '.join(allow_list)}")
