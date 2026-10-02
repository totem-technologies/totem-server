from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.db import IntegrityError, close_old_connections, transaction

from totem.messages.models import Conversation, ConversationMembership, Message
from totem.messages.services import (
    MessageAccessDenied,
    MessageValidationError,
    _encode_cursor,
    can_users_message,
    create_message,
    get_or_create_conversation,
    inbox_page,
    mark_conversation_read,
    message_page,
    sync_page,
)
from totem.rooms.models import Room
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory

from .helpers import relationship


@pytest.mark.django_db
class TestMessageAuthorization:
    def test_valid_attendee_relationship(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)

        assert can_users_message(participant, keeper)
        assert can_users_message(keeper, participant)

    def test_valid_joined_relationship(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant, attendee=False, joined=True)

        assert can_users_message(participant, keeper)
        assert can_users_message(keeper, participant)

    @pytest.mark.parametrize("actor_is_keeper", [False, True])
    def test_unrelated_users_are_denied(self, actor_is_keeper: bool):
        keeper = UserFactory()
        participant = UserFactory()

        actor, peer = (keeper, participant) if actor_is_keeper else (participant, keeper)
        assert not can_users_message(actor, peer)
        with pytest.raises(MessageAccessDenied):
            get_or_create_conversation(actor, peer)

    def test_participant_cannot_message_wrong_keeper(self):
        participant = UserFactory()
        right_keeper = UserFactory()
        wrong_keeper = UserFactory()
        relationship(right_keeper, participant)

        assert not can_users_message(participant, wrong_keeper)

    def test_keeper_cannot_message_unrelated_user(self):
        keeper = UserFactory()
        relationship(keeper, UserFactory())

        assert not can_users_message(keeper, UserFactory())

    def test_banned_participant_is_denied(self):
        keeper = UserFactory()
        participant = UserFactory()
        session = relationship(keeper, participant, joined=True)
        Room.objects.create(session=session, keeper=keeper.slug, banned_participants=[participant.slug])

        assert not can_users_message(participant, keeper)
        assert not can_users_message(keeper, participant)

    def test_ban_is_scoped_to_the_relevant_session(self):
        keeper = UserFactory()
        participant = UserFactory()
        banned_session = relationship(keeper, participant)
        relationship(keeper, participant)
        Room.objects.create(
            session=banned_session,
            keeper=keeper.slug,
            banned_participants=[participant.slug],
        )

        assert can_users_message(participant, keeper)
        assert can_users_message(keeper, participant)

    def test_unlisted_relationship_must_be_visible_to_both_users(self):
        keeper = UserFactory()
        participant = UserFactory()
        session = relationship(keeper, participant, listed=False)

        assert not can_users_message(participant, keeper)
        assert not can_users_message(keeper, participant)

        session.attendees.add(keeper)
        assert can_users_message(participant, keeper)
        assert can_users_message(keeper, participant)

    @pytest.mark.parametrize(
        "session_fields",
        [
            {"cancelled": True},
            {"space__published": False},
        ],
    )
    def test_invalid_session_relationship_is_denied(self, session_fields: dict[str, bool]):
        keeper = UserFactory()
        participant = UserFactory()
        space = SpaceFactory(author=keeper, published=session_fields.get("space__published", True))
        session = SessionFactory(space=space, cancelled=session_fields.get("cancelled", False))
        session.attendees.add(participant)

        assert not can_users_message(participant, keeper)
        assert not can_users_message(keeper, participant)

    def test_existing_conversation_is_reauthorized(self):
        keeper = UserFactory()
        participant = UserFactory()
        session = relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        session.cancelled = True
        session.save(update_fields=["cancelled"])

        with pytest.raises(MessageAccessDenied):
            create_message(conversation, participant, "No longer allowed", None)


@pytest.mark.django_db(transaction=True)
class TestConversationPersistence:
    def test_pair_is_canonical_and_has_exactly_two_memberships(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)

        first = get_or_create_conversation(participant, keeper)
        second = get_or_create_conversation(keeper, participant)

        assert first.pk == second.pk
        assert Conversation.objects.count() == 1
        assert set(first.memberships.values_list("user_id", flat=True)) == {keeper.pk, participant.pk}
        assert set(first.memberships.values_list("slot", flat=True)) == {"low", "high"}
        assert first.memberships.count() == 2

    def test_membership_slots_cap_conversation_at_two_rows(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)

        with pytest.raises(IntegrityError), transaction.atomic():
            ConversationMembership.objects.create(
                conversation=conversation,
                user=UserFactory(),
                slot=ConversationMembership.Slot.LOW,
            )

    def test_concurrent_open_returns_one_conversation(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)

        def open_conversation() -> str:
            close_old_connections()
            actor = User.objects.get(pk=participant.pk)
            peer = User.objects.get(pk=keeper.pk)
            try:
                return str(get_or_create_conversation(actor, peer).pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(lambda _: open_conversation(), range(2)))

        assert len(set(ids)) == 1
        assert Conversation.objects.count() == 1
        assert ConversationMembership.objects.count() == 2

    def test_client_message_id_returns_canonical_message(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)

        client_message_id = uuid4()
        first = create_message(conversation, participant, "Hello", client_message_id)
        duplicate = create_message(conversation, participant, "Changed retry body", client_message_id)

        assert duplicate.pk == first.pk
        assert duplicate.body == "Hello"
        assert Message.objects.count() == 1

    def test_blank_client_message_id_is_rejected(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)

        with pytest.raises(MessageValidationError, match="must be a UUID"):
            create_message(conversation, participant, "Hello", "   ")

    def test_message_cursor_is_scoped_to_its_conversation(self):
        participant = UserFactory()
        first_keeper = UserFactory()
        second_keeper = UserFactory()
        relationship(first_keeper, participant)
        relationship(second_keeper, participant)
        first_conversation = get_or_create_conversation(participant, first_keeper)
        second_conversation = get_or_create_conversation(participant, second_keeper)
        for index in range(3):
            create_message(first_conversation, participant, f"Message {index}", None)
        _page, cursor, _next_after, _has_more = message_page(first_conversation, participant, before=None, limit=1)

        with pytest.raises(MessageValidationError, match="Invalid cursor"):
            message_page(second_conversation, participant, before=cursor, limit=1)

    def test_message_is_immutable(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        message = create_message(get_or_create_conversation(participant, keeper), participant, "Hello", None)
        message.body = "Edited"

        with pytest.raises(ValueError, match="immutable"):
            message.save()
        with pytest.raises(ValueError, match="immutable"):
            message.delete()

    def test_equal_timestamp_paging_is_stable(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        messages = [create_message(conversation, participant, f"Message {index}", None) for index in range(5)]
        tied_at = datetime(2026, 1, 1, tzinfo=UTC)
        Message.objects.filter(pk__in=[message.pk for message in messages]).update(created_at=tied_at)

        first_page, next_before, _next_after, has_more = message_page(conversation, participant, before=None, limit=2)
        second_page, final_before, _next_after, final_has_more = message_page(
            conversation, participant, before=next_before, limit=3
        )

        ids = [message.pk for message in first_page + second_page]
        assert len(ids) == len(set(ids)) == 5
        assert ids == sorted(ids, reverse=True)
        assert has_more is True
        assert final_before is None
        assert final_has_more is False

    def test_inbox_and_sync_cursors_are_stable_with_equal_timestamps(self):
        participant = UserFactory()
        conversations = []
        for _ in range(3):
            keeper = UserFactory()
            relationship(keeper, participant)
            conversations.append(get_or_create_conversation(participant, keeper))
        tied_at = datetime(2026, 2, 1, tzinfo=UTC)
        Conversation.objects.filter(pk__in=[conversation.pk for conversation in conversations]).update(
            last_activity_at=tied_at
        )
        ConversationMembership.objects.filter(user=participant).update(updated_at=tied_at, sync_version=0)

        inbox_first, inbox_cursor, _unread_count = inbox_page(participant, cursor=None, limit=2)
        inbox_second, _next_cursor, _unread_count = inbox_page(participant, cursor=inbox_cursor, limit=2)
        sync_first, _removed_ids, sync_cursor, _unread_count = sync_page(participant, since=None, limit=2)
        sync_second, _removed_ids, _next_cursor, _unread_count = sync_page(participant, since=sync_cursor, limit=2)

        inbox_ids = [summary.conversation.pk for summary in inbox_first + inbox_second]
        sync_ids = [summary.membership.pk for summary in sync_first + sync_second]
        assert inbox_ids == sorted(inbox_ids, reverse=True)
        assert sync_ids == sorted(sync_ids)
        assert len(inbox_ids) == len(set(inbox_ids)) == 3
        assert len(sync_ids) == len(set(sync_ids)) == 3

    def test_sync_accepts_legacy_timestamp_cursor_as_a_safe_replay(self):
        participant = UserFactory()
        keeper = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        membership = ConversationMembership.objects.get(conversation=conversation, user=participant)
        legacy_cursor = _encode_cursor(
            membership.updated_at,
            membership.pk,
            kind="sync",
            scope=str(participant.pk),
        )

        summaries, _removed_ids, _next_cursor, _unread_count = sync_page(
            participant,
            since=legacy_cursor,
            limit=10,
        )

        assert [summary.conversation.pk for summary in summaries] == [conversation.pk]

    def test_sync_advances_past_revoked_memberships(self):
        participant = UserFactory()
        revoked_keeper = UserFactory()
        active_keeper = UserFactory()
        revoked_session = relationship(revoked_keeper, participant)
        revoked_conversation = get_or_create_conversation(participant, revoked_keeper)
        relationship(active_keeper, participant)
        active_conversation = get_or_create_conversation(participant, active_keeper)
        revoked_session.cancelled = True
        revoked_session.save(update_fields=["cancelled"])

        first, removed_ids, cursor, _unread_count = sync_page(participant, since=None, limit=1)
        second, second_removed_ids, _next_cursor, _unread_count = sync_page(participant, since=cursor, limit=1)

        assert first == []
        assert removed_ids == [revoked_conversation.pk]
        assert cursor is not None
        assert [summary.conversation.pk for summary in second] == [active_conversation.pk]
        assert second_removed_ids == [revoked_conversation.pk]

    def test_inbox_cursor_is_scoped_to_its_user(self):
        first_participant = UserFactory()
        first_keeper = UserFactory()
        relationship(first_keeper, first_participant)
        first_conversation = get_or_create_conversation(first_participant, first_keeper)
        second_keeper = UserFactory()
        relationship(second_keeper, first_participant)
        get_or_create_conversation(first_participant, second_keeper)
        _page, cursor, _unread_count = inbox_page(first_participant, cursor=None, limit=1)
        assert first_conversation is not None
        assert cursor is not None

        other_participant = UserFactory()
        other_keeper = UserFactory()
        relationship(other_keeper, other_participant)
        get_or_create_conversation(other_participant, other_keeper)

        with pytest.raises(MessageValidationError, match="Invalid cursor"):
            inbox_page(other_participant, cursor=cursor, limit=1)

    def test_marking_first_message_recomputes_later_peer_messages_as_unread(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        first = create_message(conversation, keeper, "First", None)
        create_message(conversation, keeper, "Second", None)
        create_message(conversation, keeper, "Third", None)

        membership = mark_conversation_read(conversation, participant, first.pk)

        assert membership.last_read_message_id == first.pk
        assert membership.unread_count == 2

    def test_read_state_only_advances_and_unread_excludes_sender(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        first = create_message(conversation, keeper, "First", None)
        second = create_message(conversation, keeper, "Second", None)
        create_message(conversation, participant, "My own message", None)

        membership = mark_conversation_read(conversation, participant, second.pk)
        membership = mark_conversation_read(conversation, participant, first.pk)

        assert membership.last_read_message_id == second.pk
        assert membership.unread_count == 0
        assert ConversationMembership.objects.get(conversation=conversation, user=keeper).unread_count == 1
