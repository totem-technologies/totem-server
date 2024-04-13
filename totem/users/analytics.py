from typing import TYPE_CHECKING

from django.conf import settings
from posthog import Posthog

if TYPE_CHECKING:
    from totem.circles.models import CircleEvent
    from totem.users.models import User

_posthog = None


def _get_posthog() -> Posthog | None:
    if settings.DEBUG:
        return
    if not settings.POSTHOG_API_KEY:
        return
    global _posthog
    _posthog = Posthog(project_api_key=settings.POSTHOG_API_KEY, host="https://app.posthog.com")
    return _posthog


def identify_user(user: "User"):
    if p := _get_posthog():
        p.identify(
            user.analytics_id(),
            {
                "environment": settings.ENVIRONMENT_NAME.lower(),
                "staff": user.is_staff,
            },
        )


def user_signed_up(user: "User"):
    if p := _get_posthog():
        p.capture(user.analytics_id(), "user_signed_up")


def user_onboarded(user: "User"):
    if p := _get_posthog():
        p.capture(user.analytics_id(), "user_onboarded")


def event_joined(user: "User", event: "CircleEvent"):
    if p := _get_posthog():
        p.capture(user.analytics_id(), "event_joined", {"event_id": event.slug, "circle_id": event.circle.slug})
