from typing import TYPE_CHECKING

from django.conf import settings
from posthog import Posthog

if TYPE_CHECKING:
    from totem.spaces.models import Session
    from totem.users.models import User

_posthog = Posthog(project_api_key=settings.POSTHOG_API_KEY, host="https://us.i.posthog.com")
if settings.DEBUG or settings.TEST or "test" in settings.POSTHOG_API_KEY:
    _posthog.debug = True
    _posthog.disabled = True


def identify_user(user: "User"):
    _posthog.capture(
        "identify",
        distinct_id=user.analytics_id(),
        properties={
            "$set": {"environment": settings.ENVIRONMENT_NAME.lower(), "staff": user.is_staff},
        },
    )


def user_signed_up(user: "User"):
    _posthog.capture("user_signed_up", distinct_id=user.analytics_id())


def user_onboarded(user: "User"):
    _posthog.capture("user_onboarded", distinct_id=user.analytics_id())


def session_joined(user: "User", session: "Session"):
    _posthog.capture(
        "session_joined",
        distinct_id=user.analytics_id(),
        properties={
            "session_id": session.slug,
            "space_id": session.space.slug,
            "keeper_id": session.space.author.analytics_id(),
        },
    )
