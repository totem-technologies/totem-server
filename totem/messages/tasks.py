import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from totem.notifications.services import send_notification_to_user
from totem.spaces.models import Session
from totem.users.models import User

from .models import AutomationPrompt
from .services import can_users_message, session_allows_messaging
from .services import retry_unread_message_notifications as retry_message_notifications

logger = logging.getLogger(__name__)


def _completion_time(session: Session) -> datetime | None:
    return session.completion_time() if session.ended() else None


def _completed_sessions(delay_minutes: int) -> list[Session]:
    now = timezone.now()
    latest_completion = now - timedelta(minutes=delay_minutes)
    earliest_completion = now - timedelta(hours=settings.MESSAGING_AUTOMATION_LOOKBACK_HOURS)
    candidates = (
        Session.objects.filter(cancelled=False, start__lt=latest_completion)
        .filter(Q(ended_at__gte=earliest_completion) | Q(start__gte=earliest_completion - timedelta(hours=5)))
        .select_related("space", "space__author", "room")
    )
    return [
        session
        for session in candidates
        if (completion := _completion_time(session)) is not None
        and earliest_completion <= completion <= latest_completion
    ]


def _eligible_participants(session: Session) -> list[User]:
    keeper = session.space.author
    participants = (
        User.objects.filter(Q(sessions_attending=session) | Q(sessions_joined=session), is_active=True)
        .exclude(pk=keeper.pk)
        .exclude(slug__in=session.banned_slugs())
        .distinct()
    )
    return [participant for participant in participants if session_allows_messaging(session, keeper, participant)]


def _deliver_prompt(
    prompt: AutomationPrompt,
    *,
    title: str,
    body: str,
    data: dict[str, str],
) -> bool:
    try:
        with transaction.atomic():
            locked_prompt = AutomationPrompt.objects.select_for_update().select_related("recipient").get(pk=prompt.pk)
            if locked_prompt.status != AutomationPrompt.Status.PENDING:
                return False
            # NOTE: This holds one row lock during FCM delivery; move to a transactional outbox if task volume grows.
            delivered = send_notification_to_user(locked_prompt.recipient, title=title, body=body, data=data)
            if delivered:
                locked_prompt.mark_delivered()
            return delivered
    except Exception:
        logger.exception("Failed to deliver messaging automation prompt %s", prompt.pk)
        return False


def create_keeper_follow_up_prompts() -> int:
    if not settings.MESSAGING_KEEPER_FOLLOW_UP_ENABLED:
        return 0
    processed = 0
    for session in _completed_sessions(settings.MESSAGING_KEEPER_FOLLOW_UP_DELAY_MINUTES):
        keeper = session.space.author
        if not _eligible_participants(session):
            continue
        prompt, created = AutomationPrompt.objects.get_or_create(
            idempotency_key=f"session:{session.pk}:keeper-follow-up:{keeper.pk}",
            defaults={
                "recipient": keeper,
                "session": session,
                "kind": AutomationPrompt.Kind.KEEPER_FOLLOW_UP,
            },
        )
        if not settings.MESSAGING_KEEPER_FOLLOW_UP_NOTIFY_ENABLED:
            processed += int(created)
            continue
        processed += int(
            _deliver_prompt(
                prompt,
                title="Follow up after your Totem session",
                body="Your participant list is ready.",
                data={
                    "type": "post_session_follow_up",
                    "prompt_id": str(prompt.pk),
                    "session_slug": session.slug,
                    "path": f"/messages/sessions/{session.slug}/participants",
                },
            )
        )
    return processed


def create_share_upcoming_space_prompts() -> int:
    if not settings.MESSAGING_SHARE_UPCOMING_SPACE_ENABLED:
        return 0
    created_count = 0
    for session in _completed_sessions(settings.MESSAGING_SHARE_UPCOMING_SPACE_DELAY_MINUTES):
        keeper = session.space.author
        if not _eligible_participants(session):
            continue
        has_upcoming_session = (
            Session.objects.visible_to(keeper)
            .not_ended()
            .filter(space__author=keeper, start__gt=timezone.now())
            .exists()
        )
        if not has_upcoming_session:
            continue
        _prompt, created = AutomationPrompt.objects.get_or_create(
            idempotency_key=f"session:{session.pk}:share-upcoming-space:{keeper.pk}",
            defaults={
                "recipient": keeper,
                "session": session,
                "kind": AutomationPrompt.Kind.SHARE_UPCOMING_SPACE,
            },
        )
        created_count += int(created)
    return created_count


def retry_unread_message_notifications() -> int:
    if not settings.MESSAGING_DIRECT_MESSAGE_RETRY_ENABLED:
        return 0
    return retry_message_notifications()


def send_post_session_discovery_nudges() -> int:
    if not settings.MESSAGING_DISCOVERY_NUDGE_ENABLED:
        return 0
    delivered_count = 0
    for session in _completed_sessions(settings.MESSAGING_DISCOVERY_NUDGE_DELAY_MINUTES):
        keeper = session.space.author
        for participant in _eligible_participants(session):
            if not can_users_message(participant, keeper):
                continue
            prompt, _created = AutomationPrompt.objects.get_or_create(
                idempotency_key=f"session:{session.pk}:participant-discovery:{participant.pk}",
                defaults={
                    "recipient": participant,
                    "session": session,
                    "kind": AutomationPrompt.Kind.PARTICIPANT_DISCOVERY,
                },
            )
            delivered_count += int(
                _deliver_prompt(
                    prompt,
                    title="Discover another Totem space",
                    body="Find another support space when you are ready.",
                    data={
                        "type": "post_session_discovery",
                        "prompt_id": str(prompt.pk),
                        "path": "/spaces",
                    },
                )
            )
    return delivered_count


tasks = [
    create_keeper_follow_up_prompts,
    create_share_upcoming_space_prompts,
    send_post_session_discovery_nudges,
    retry_unread_message_notifications,
]
