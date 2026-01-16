from typing import TypedDict

from django.urls import reverse

from totem.users.actions_base import ActionBase


class SubscribeSpaceParameters(TypedDict):
    space_slug: str
    subscribe: bool


class SubscribeSpaceAction(ActionBase[SubscribeSpaceParameters]):
    action_id = "spaces:subscribe"

    def get_url(self):
        slug = self.parameters.get("space_slug") or self.parameters.get("circle_slug")
        if slug is None:
            raise KeyError("space_slug")
        return reverse(self.action_id, kwargs={"slug": slug})


class JoinSessionParameters(TypedDict):
    session_slug: str


class JoinSessionAction(ActionBase[JoinSessionParameters]):
    action_id = "spaces:join"

    def get_url(self) -> str:
        slug = self.parameters.get("session_slug") or self.parameters.get("event_slug")
        if slug is None:
            raise KeyError("session_slug")
        return reverse("spaces:join", kwargs={"session_slug": slug})


SubscribeActionParameters = SubscribeSpaceParameters
SubscribeAction = SubscribeSpaceAction
JoinCircleParameters = JoinSessionParameters
JoinCircleAction = JoinSessionAction
