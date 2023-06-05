from django.conf import settings
from posthog import Posthog

posthog = Posthog(project_api_key=settings.POSTHOG_API_KEY, host="https://app.posthog.com")


def identify_user(user):
    if settings.DEBUG:
        return
    posthog.identify(
        user.analytics_id(),
        {
            "environment": settings.ENVIRONMENT_NAME.lower(),
            "staff": user.is_staff,
        },
    )
