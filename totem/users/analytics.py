from typing import TYPE_CHECKING

from django.conf import settings
from posthog import Posthog

if TYPE_CHECKING:
    from totem.circles.models import CircleEvent
    from totem.users.models import User

_posthog = Posthog(project_api_key=settings.POSTHOG_API_KEY, host="https://us.i.posthog.com")
if settings.DEBUG or "test" in settings.POSTHOG_API_KEY:
    _posthog.debug = True
    _posthog.disabled = True


def identify_user(user: "User"):
    _posthog.identify(
        user.analytics_id(),
        {
            "environment": settings.ENVIRONMENT_NAME.lower(),
            "staff": user.is_staff,
        },
    )


def user_signed_up(user: "User"):
    _posthog.capture(user.analytics_id(), "user_signed_up")


def user_onboarded(user: "User"):
    _posthog.capture(user.analytics_id(), "user_onboarded")


def event_joined(user: "User", event: "CircleEvent"):
    _posthog.capture(
        user.analytics_id(),
        "event_joined",
        {"event_id": event.slug, "circle_id": event.circle.slug, "keeper_id": event.circle.author.analytics_id()},
    )
