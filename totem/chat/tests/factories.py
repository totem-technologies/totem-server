from factory import SubFactory
from factory.django import DjangoModelFactory

from totem.chat.models import ChatMessage, ChatParticipant, ChatRoom
from totem.users.tests.factories import UserFactory
from totem.utils.factories import BaseMetaFactory


class ChatRoomFactory(DjangoModelFactory, metaclass=BaseMetaFactory[ChatRoom]):
    room_type = ChatRoom.RoomType.DIRECT

    class Meta:
        model = ChatRoom


class ChatParticipantFactory(DjangoModelFactory, metaclass=BaseMetaFactory[ChatParticipant]):
    room = SubFactory(ChatRoomFactory)
    user = SubFactory(UserFactory)

    class Meta:
        model = ChatParticipant
        django_get_or_create = ["room", "user"]


class ChatMessageFactory(DjangoModelFactory, metaclass=BaseMetaFactory[ChatMessage]):
    room = SubFactory(ChatRoomFactory)
    sender = SubFactory(UserFactory)
    content = "Test message content"

    class Meta:
        model = ChatMessage
