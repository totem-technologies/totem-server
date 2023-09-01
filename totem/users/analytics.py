from django.conf import settings
from posthog import Posthog

_posthog = None


def _get_posthog():
    global _posthog
    _posthog = Posthog(project_api_key=settings.POSTHOG_API_KEY, host="https://app.posthog.com")
    return _posthog


def identify_user(user):
    if settings.DEBUG:
        return
    if not settings.POSTHOG_API_KEY:
        return
    _get_posthog().identify(
        user.analytics_id(),
        {
            "environment": settings.ENVIRONMENT_NAME.lower(),
            "staff": user.is_staff,
        },
    )
