import uuid

import pytest

from totem.chat.models import ChatMessage, ChatParticipant, ChatRoom
from totem.chat.tests.factories import (
    ChatMessageFactory,
    ChatParticipantFactory,
    ChatRoomFactory,
)
from totem.users.tests.factories import UserFactory


class TestChatRoom:
    def test_create_direct_room(self, db):
        room = ChatRoomFactory(room_type=ChatRoom.RoomType.DIRECT)
        assert room.id is not None
        assert room.room_type == ChatRoom.RoomType.DIRECT
        assert room.session is None

    def test_create_session_room(self, db):
        room = ChatRoomFactory(room_type=ChatRoom.RoomType.SESSION)
        assert room.room_type == ChatRoom.RoomType.SESSION

    def test_create_group_room(self, db):
        room = ChatRoomFactory(room_type=ChatRoom.RoomType.GROUP)
        assert room.room_type == ChatRoom.RoomType.GROUP

    def test_str(self, db):
        room = ChatRoomFactory()
        assert str(room).startswith("<ChatRoom:")


class TestChatParticipant:
    def test_create_participant(self, db):
        participant = ChatParticipantFactory()
        assert participant.id is not None
        assert participant.room is not None
        assert participant.user is not None
        assert participant.last_read_at is not None

    def test_unique_together(self, db):
        participant = ChatParticipantFactory()
        with pytest.raises(Exception):
            ChatParticipant.objects.create(
                room=participant.room,
                user=participant.user,
            )

    def test_str(self, db):
        participant = ChatParticipantFactory()
        assert str(participant).startswith("<ChatParticipant:")


class TestChatMessage:
    def test_create_message(self, db):
        message = ChatMessageFactory()
        assert message.id is not None
        assert message.room is not None
        assert message.sender is not None
        assert message.content == "Test message content"
        assert message.created_at is not None

    def test_client_id_unique(self, db):
        cid = uuid.uuid4()
        ChatMessageFactory(client_id=cid)
        with pytest.raises(Exception):
            ChatMessageFactory(client_id=cid)

    def test_client_id_nullable(self, db):
        message = ChatMessageFactory(client_id=None)
        assert message.client_id is None

    def test_str(self, db):
        message = ChatMessageFactory()
        assert str(message).startswith("<ChatMessage:")

    def test_ordering_desc(self, db):
        room = ChatRoomFactory()
        sender = UserFactory()
        msg1 = ChatMessageFactory(room=room, sender=sender)
        msg2 = ChatMessageFactory(room=room, sender=sender)
        messages = list(ChatMessage.objects.filter(room=room))
        # Most recent first
        assert messages[0].id == msg2.id
        assert messages[1].id == msg1.id
