import uuid

import pytest
from django.test import Client
from django.urls import reverse

from totem.api.auth import generate_jwt_token
from totem.chat.models import ChatMessage, ChatParticipant, ChatRoom
from totem.chat.tests.factories import (
    ChatMessageFactory,
    ChatParticipantFactory,
    ChatRoomFactory,
)
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory


@pytest.fixture
def auth_user(db):
    return UserFactory(email="chat_test@example.com")


@pytest.fixture
def auth_token(auth_user):
    return generate_jwt_token(auth_user)


@pytest.fixture
def auth_header(auth_token):
    return f"Bearer {auth_token}"


@pytest.fixture
def other_user(db):
    return UserFactory(email="other@example.com")


@pytest.fixture
def direct_room(auth_user, other_user):
    room = ChatRoomFactory(room_type=ChatRoom.RoomType.DIRECT)
    ChatParticipantFactory(room=room, user=auth_user)
    ChatParticipantFactory(room=room, user=other_user)
    return room


class TestListThreads:
    def test_list_threads_empty(self, client: Client, db, auth_header):
        response = client.get(
            reverse("mobile-api:chat_list_threads"),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_threads_with_data(self, client: Client, db, auth_user, auth_header, direct_room):
        ChatMessageFactory(room=direct_room, sender=auth_user, content="Hello")

        response = client.get(
            reverse("mobile-api:chat_list_threads"),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(direct_room.id)
        assert data[0]["room_type"] == ChatRoom.RoomType.DIRECT
        assert isinstance(data[0]["unread_count"], int)
        assert data[0]["last_message"] is not None

    def test_list_threads_unread_count(self, client: Client, db, auth_user, other_user, auth_header):
        room = ChatRoomFactory()
        ChatParticipantFactory(room=room, user=auth_user)
        ChatParticipantFactory(room=room, user=other_user)
        # Other user sends a message
        ChatMessageFactory(room=room, sender=other_user, content="Hey!")
        ChatMessageFactory(room=room, sender=other_user, content="You there?")

        response = client.get(
            reverse("mobile-api:chat_list_threads"),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["unread_count"] == 2

    def test_list_threads_no_unread_for_own_messages(self, client: Client, db, auth_user, auth_header, direct_room):
        ChatMessageFactory(room=direct_room, sender=auth_user, content="My message")

        response = client.get(
            reverse("mobile-api:chat_list_threads"),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data[0]["unread_count"] == 0


class TestGetThreadMessages:
    def test_get_messages_empty(self, client: Client, db, auth_user, auth_header, direct_room):
        response = client.get(
            reverse("mobile-api:chat_get_messages", kwargs={"thread_id": direct_room.id}),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["next"] is None

    def test_get_messages_with_data(self, client: Client, db, auth_user, auth_header, direct_room):
        ChatMessageFactory(room=direct_room, sender=auth_user, content="First")
        ChatMessageFactory(room=direct_room, sender=auth_user, content="Second")

        response = client.get(
            reverse("mobile-api:chat_get_messages", kwargs={"thread_id": direct_room.id}),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) == 2
        # Most recent first
        assert results[0]["content"] == "Second"

    def test_get_messages_not_participant(self, client: Client, db, auth_user, auth_header):
        room = ChatRoomFactory()
        # auth_user is NOT a participant
        response = client.get(
            reverse("mobile-api:chat_get_messages", kwargs={"thread_id": room.id}),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 404

    def test_get_messages_updates_last_read(self, client: Client, db, auth_user, auth_header, direct_room):
        old_last_read = ChatParticipant.objects.get(room=direct_room, user=auth_user).last_read_at

        response = client.get(
            reverse("mobile-api:chat_get_messages", kwargs={"thread_id": direct_room.id}),
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200

        new_last_read = ChatParticipant.objects.get(room=direct_room, user=auth_user).last_read_at
        assert new_last_read >= old_last_read


class TestSendMessage:
    def test_send_message_success(self, client: Client, db, auth_user, auth_header, direct_room):
        cid = uuid.uuid4()
        payload = {"content": "Hello world", "client_id": str(cid)}

        response = client.post(
            reverse("mobile-api:chat_send_message", kwargs={"thread_id": direct_room.id}),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Hello world"
        assert data["sender_id"] == auth_user.id
        assert data["room_id"] == str(direct_room.id)
        assert data["client_id"] == str(cid)

        # Verify in DB
        msg = ChatMessage.objects.get(client_id=cid)
        assert msg.content == "Hello world"

    def test_send_message_idempotent(self, client: Client, db, auth_user, auth_header, direct_room):
        cid = uuid.uuid4()
        payload = {"content": "Hello world", "client_id": str(cid)}

        # First send
        r1 = client.post(
            reverse("mobile-api:chat_send_message", kwargs={"thread_id": direct_room.id}),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert r1.status_code == 200

        # Second send with same client_id
        r2 = client.post(
            reverse("mobile-api:chat_send_message", kwargs={"thread_id": direct_room.id}),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]

        # Only one message in DB
        assert ChatMessage.objects.filter(client_id=cid).count() == 1

    def test_send_message_not_participant(self, client: Client, db, auth_user, auth_header):
        room = ChatRoomFactory()
        payload = {"content": "Hello", "client_id": str(uuid.uuid4())}

        response = client.post(
            reverse("mobile-api:chat_send_message", kwargs={"thread_id": room.id}),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 404

    def test_send_message_content_too_long(self, client: Client, db, auth_user, auth_header, direct_room):
        payload = {"content": "x" * 10001, "client_id": str(uuid.uuid4())}

        response = client.post(
            reverse("mobile-api:chat_send_message", kwargs={"thread_id": direct_room.id}),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 422


class TestKeeperBulkMessage:
    def test_bulk_message_creates_direct_rooms(self, client: Client, db, auth_user, auth_header):
        session = SessionFactory()
        target1 = UserFactory(email="target1@example.com")
        target2 = UserFactory(email="target2@example.com")
        payload = {
            "user_ids": [target1.id, target2.id],
            "content": "Bulk message from keeper",
            "session_id": session.id,
        }

        response = client.post(
            reverse("mobile-api:chat_keeper_bulk"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Verify rooms and messages created
        for target in [target1, target2]:
            rooms = ChatRoom.objects.filter(
                room_type=ChatRoom.RoomType.DIRECT,
                participants__user=auth_user,
            ).filter(participants__user=target)
            assert rooms.exists()
            room = rooms.first()
            assert room is not None

            messages = ChatMessage.objects.filter(room=room, sender=auth_user)
            assert messages.exists()
            assert messages.first().content == "Bulk message from keeper"  # type: ignore[union-attr]

    def test_bulk_message_reuses_existing_rooms(self, client: Client, db, auth_user, auth_header):
        session = SessionFactory()
        target = UserFactory(email="target@example.com")
        # Create existing direct room
        existing_room = ChatRoomFactory(room_type=ChatRoom.RoomType.DIRECT)
        ChatParticipantFactory(room=existing_room, user=auth_user)
        ChatParticipantFactory(room=existing_room, user=target)

        payload = {
            "user_ids": [target.id],
            "content": "Follow-up",
            "session_id": session.id,
        }

        response = client.post(
            reverse("mobile-api:chat_keeper_bulk"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        # Should have reused the existing room
        rooms_count = (
            ChatRoom.objects.filter(
                room_type=ChatRoom.RoomType.DIRECT,
                participants__user=auth_user,
            )
            .filter(participants__user=target)
            .count()
        )
        assert rooms_count == 1

    def test_bulk_message_empty_user_list(self, client: Client, db, auth_header):
        session = SessionFactory()
        payload = {
            "user_ids": [],
            "content": "Bulk message",
            "session_id": session.id,
        }

        response = client.post(
            reverse("mobile-api:chat_keeper_bulk"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 422


class TestCheckUpdates:
    def test_check_updates_no_cache(self, client: Client, db, auth_user, auth_header, direct_room):
        response = client.get(
            reverse(
                "mobile-api:chat_check_updates",
                kwargs={"thread_id": direct_room.id},
            )
            + "?client_last_time=0.0",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_updates"] is True

    def test_check_updates_not_participant(self, client: Client, db, auth_user, auth_header):
        room = ChatRoomFactory()
        response = client.get(
            reverse(
                "mobile-api:chat_check_updates",
                kwargs={"thread_id": room.id},
            )
            + "?client_last_time=0.0",
            HTTP_AUTHORIZATION=auth_header,
        )
        assert response.status_code == 404
