import urllib.parse
from abc import ABC
from dataclasses import asdict, dataclass
from typing import Generic, TypeVar

from django.conf import settings
from django.urls import reverse

from totem.users.models import ActionToken, User

T = TypeVar("T", bound=type(dataclass))


class ActionBase(Generic[T], ABC):
    action_id: str
    __parameters_type__: type[T]

    class ActionExpired(Exception):
        pass

    @classmethod
    def build_url(cls, user: User, parameters: T) -> str:
        token = ActionToken.objects.create(
            user=user,
            action=cls.action_id,
            parameters=asdict(parameters),
        )
        link = cls.get_url(parameters=parameters) + f"?token={token.token}"
        return urllib.parse.urljoin(settings.EMAIL_BASE_URL, link)

    @classmethod
    def resolve(cls, token: str) -> tuple[User, T]:
        try:
            action_token = ActionToken.objects.get(token=token)
        except ActionToken.DoesNotExist:
            raise cls.ActionExpired()
        if not action_token.is_valid():
            raise cls.ActionExpired()
        return action_token.user, cls.__parameters_type__(**action_token.parameters)

    @classmethod
    def get_url(cls, parameters: T) -> str:
        return reverse(cls.action_id)
