from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import close_old_connections
from django.utils import timezone

from totem.messages.models import AutomationPrompt, Message, MessageNotification
from totem.messages.services import create_message, get_or_create_conversation, mark_conversation_read
from totem.messages.tasks import (
    create_keeper_follow_up_prompts,
    create_share_upcoming_space_prompts,
    retry_unread_message_notifications,
    send_post_session_discovery_nudges,
)
from totem.notifications.models import FCMDevice
from totem.rooms.models import Room
from totem.spaces.models import Space
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.tests.factories import KeeperProfileFactory, UserFactory


def completed_session(*, provider=Space.MeetingProviderChoices.GOOGLE_MEET):
    keeper = UserFactory()
    KeeperProfileFactory(user=keeper)
    participant = UserFactory()
    session = SessionFactory(
        space=SpaceFactory(author=keeper, meeting_provider=provider),
        start=timezone.now() - timedelta(hours=2),
        ended_at=timezone.now() - timedelta(minutes=40),
    )
    session.attendees.add(participant)
    session.joined.add(participant)
    return session, keeper, participant


@pytest.mark.django_db
class TestPostSessionMessagingTasks:
    def test_keeper_follow_up_is_idempotent_and_has_string_only_deep_link_data(self, settings):
        settings.MESSAGING_KEEPER_FOLLOW_UP_ENABLED = True
        settings.MESSAGING_KEEPER_FOLLOW_UP_NOTIFY_ENABLED = True
        session, keeper, _participant = completed_session()

        with patch("totem.messages.tasks.send_notification_to_user", return_value=True) as send:
            assert create_keeper_follow_up_prompts() == 1
            assert create_keeper_follow_up_prompts() == 0

        prompt = AutomationPrompt.objects.get(kind=AutomationPrompt.Kind.KEEPER_FOLLOW_UP)
        assert prompt.recipient == keeper
        assert prompt.session == session
        assert prompt.status == AutomationPrompt.Status.DELIVERED
        assert prompt.delivered_at is not None
        send.assert_called_once()
        assert send.call_args.kwargs["data"]["path"] == f"/messages/sessions/{session.slug}/participants"
        assert all(isinstance(value, str) for value in send.call_args.kwargs["data"].values())

    def test_recent_ended_at_is_used_even_when_session_started_before_lookback(self, settings):
        settings.MESSAGING_KEEPER_FOLLOW_UP_ENABLED = True
        session, _keeper, _participant = completed_session(provider=Space.MeetingProviderChoices.LIVEKIT)
        session.start = timezone.now() - timedelta(days=2)
        session.save(update_fields=["start"])

        assert create_keeper_follow_up_prompts() == 1

    def test_livekit_scheduled_end_is_not_treated_as_completion(self, settings):
        settings.MESSAGING_KEEPER_FOLLOW_UP_ENABLED = True
        session, _keeper, _participant = completed_session(provider=Space.MeetingProviderChoices.LIVEKIT)
        session.ended_at = None
        session.start = timezone.now() - timedelta(hours=2)
        session.save(update_fields=["ended_at", "start"])

        assert create_keeper_follow_up_prompts() == 0
        assert AutomationPrompt.objects.count() == 0

    def test_share_upcoming_space_creates_dismissible_action_but_no_message(self, settings):
        settings.MESSAGING_SHARE_UPCOMING_SPACE_ENABLED = True
        session, keeper, _participant = completed_session()
        SessionFactory(space=SpaceFactory(author=keeper), start=timezone.now() + timedelta(days=2))

        assert create_share_upcoming_space_prompts() == 1
        assert create_share_upcoming_space_prompts() == 0

        prompt = AutomationPrompt.objects.get(kind=AutomationPrompt.Kind.SHARE_UPCOMING_SPACE)
        assert prompt.session == session
        assert prompt.status == AutomationPrompt.Status.PENDING
        prompt.dismiss()
        prompt.refresh_from_db()
        assert prompt.status == AutomationPrompt.Status.DISMISSED
        assert prompt.dismissed_at is not None
        assert Message.objects.count() == 0

    def test_discovery_nudge_excludes_banned_and_is_idempotent(self, settings):
        settings.MESSAGING_DISCOVERY_NUDGE_ENABLED = True
        session, keeper, participant = completed_session()
        banned = UserFactory()
        session.attendees.add(banned)
        Room.objects.create(session=session, keeper=keeper.slug, banned_participants=[banned.slug])

        with patch("totem.messages.tasks.send_notification_to_user", return_value=True) as send:
            assert send_post_session_discovery_nudges() == 1
            assert send_post_session_discovery_nudges() == 0

        prompt = AutomationPrompt.objects.get(kind=AutomationPrompt.Kind.PARTICIPANT_DISCOVERY)
        assert prompt.recipient == participant
        assert prompt.status == AutomationPrompt.Status.DELIVERED
        assert not AutomationPrompt.objects.filter(recipient=banned).exists()
        send.assert_called_once()
        assert send.call_args.args[0] == participant
        assert send.call_args.kwargs["data"] == {
            "type": "post_session_discovery",
            "prompt_id": str(prompt.pk),
            "path": "/spaces",
        }

    def test_discovery_nudge_respects_device_opt_out(self, settings):
        settings.MESSAGING_DISCOVERY_NUDGE_ENABLED = True
        _session, _keeper, participant = completed_session()
        FCMDevice.objects.create(user=participant, token="inactive-token", active=False)

        assert send_post_session_discovery_nudges() == 0
        prompt = AutomationPrompt.objects.get(kind=AutomationPrompt.Kind.PARTICIPANT_DISCOVERY)
        assert prompt.status == AutomationPrompt.Status.PENDING
        assert prompt.delivered_at is None

    @pytest.mark.parametrize(
        ("setting_name", "task"),
        [
            ("MESSAGING_KEEPER_FOLLOW_UP_ENABLED", create_keeper_follow_up_prompts),
            ("MESSAGING_SHARE_UPCOMING_SPACE_ENABLED", create_share_upcoming_space_prompts),
            ("MESSAGING_DISCOVERY_NUDGE_ENABLED", send_post_session_discovery_nudges),
        ],
    )
    def test_automation_is_disabled_by_default(self, settings, setting_name: str, task):
        setattr(settings, setting_name, False)
        completed_session()

        assert task() == 0
        assert AutomationPrompt.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_task_runs_deliver_one_keeper_notification(settings):
    settings.MESSAGING_KEEPER_FOLLOW_UP_ENABLED = True
    settings.MESSAGING_KEEPER_FOLLOW_UP_NOTIFY_ENABLED = True
    completed_session()

    def run_task() -> int:
        close_old_connections()
        try:
            return create_keeper_follow_up_prompts()
        finally:
            close_old_connections()

    with patch("totem.messages.tasks.send_notification_to_user", return_value=True) as send:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: run_task(), range(2)))

    assert sorted(results) == [0, 1]
    send.assert_called_once()
    assert AutomationPrompt.objects.get().status == AutomationPrompt.Status.DELIVERED


@pytest.mark.django_db
class TestUnreadMessageNotificationRetry:
    def test_failed_delivery_is_retried_once_while_the_message_is_unread(self, django_capture_on_commit_callbacks):
        _session, keeper, participant = completed_session()
        conversation = get_or_create_conversation(participant, keeper)

        with (
            patch("totem.messages.services.send_notification_to_user", return_value=False),
            django_capture_on_commit_callbacks(execute=True),
        ):
            message = create_message(conversation, participant, "Need help", None)

        notification = MessageNotification.objects.get(message=message)
        assert notification.status == MessageNotification.Status.PENDING
        assert notification.attempt_count == 1
        MessageNotification.objects.filter(pk=notification.pk).update(
            last_attempt_at=timezone.now() - timedelta(minutes=16)
        )

        with patch("totem.messages.services.send_notification_to_user", return_value=True) as send:
            assert retry_unread_message_notifications() == 1
            assert retry_unread_message_notifications() == 0

        notification.refresh_from_db()
        assert notification.status == MessageNotification.Status.DELIVERED
        assert notification.attempt_count == 2
        send.assert_called_once()

    def test_reading_a_message_suppresses_a_failed_delivery_retry(self):
        _session, keeper, participant = completed_session()
        conversation = get_or_create_conversation(participant, keeper)
        message = create_message(conversation, participant, "Need help", None)
        notification = MessageNotification.objects.get(message=message)
        MessageNotification.objects.filter(pk=notification.pk).update(
            last_attempt_at=timezone.now() - timedelta(minutes=16)
        )

        mark_conversation_read(conversation, keeper, message.pk)

        with patch("totem.messages.services.send_notification_to_user") as send:
            assert retry_unread_message_notifications() == 0

        notification.refresh_from_db()
        assert notification.status == MessageNotification.Status.DISMISSED
        send.assert_not_called()

    def test_relationship_revocation_suppresses_a_failed_delivery_retry(self):
        session, keeper, participant = completed_session()
        conversation = get_or_create_conversation(participant, keeper)
        message = create_message(conversation, participant, "Need help", None)
        notification = MessageNotification.objects.get(message=message)
        MessageNotification.objects.filter(pk=notification.pk).update(
            last_attempt_at=timezone.now() - timedelta(minutes=16)
        )
        Room.objects.create(session=session, keeper=keeper.slug, banned_participants=[participant.slug])

        with patch("totem.messages.services.send_notification_to_user") as send:
            assert retry_unread_message_notifications() == 0

        notification.refresh_from_db()
        assert notification.status == MessageNotification.Status.DISMISSED
        send.assert_not_called()
