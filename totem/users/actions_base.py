import urllib.parse
from abc import ABC
from typing import Generic, TypeVar

from django.conf import settings
from django.urls import reverse

from totem.users.models import ActionToken, User

T = TypeVar("T")


class ActionBase(Generic[T], ABC):
    action_id: str
    parameters: T
    user: User

    class ActionException(Exception):
        pass

    class ActionExpired(ActionException):
        pass

    class ActionInvalid(ActionException):
        pass

    class ActionDoesNotExist(ActionException):
        pass

    def __init__(self, user: User, parameters: T) -> None:
        self.parameters = parameters
        self.user = user

    def build_url(self, expires_at=None) -> str:
        kwargs = {
            "user": self.user,
            "action": self.action_id,
            "parameters": self.parameters,
        }
        if expires_at is not None:
            kwargs["expires_at"] = expires_at
        token = ActionToken.objects.create(**kwargs)
        link = self.get_url() + f"?token={token.token}"
        return urllib.parse.urljoin(settings.SITE_BASE_URL, link)

    @classmethod
    def resolve(cls, token: str) -> tuple[User, T]:
        try:
            action_token = ActionToken.objects.get(token=token)
        except ActionToken.DoesNotExist:
            raise cls.ActionDoesNotExist()
        if not action_token.is_valid():
            raise cls.ActionExpired()
        return action_token.user, action_token.parameters

    def get_url(self) -> str:
        return reverse(self.action_id)
