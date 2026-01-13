from typing import TypedDict

from django.urls import reverse

from totem.users.actions_base import ActionBase


class SubscribeSpaceParameters(TypedDict):
    space_slug: str
    subscribe: bool


class SubscribeSpaceAction(ActionBase[SubscribeSpaceParameters]):
    action_id = "circles:subscribe"

    def get_url(self):
        slug = self.parameters.get("space_slug") or self.parameters.get("circle_slug")
        if slug is None:
            raise KeyError("space_slug")
        return reverse(self.action_id, kwargs={"slug": slug})


class JoinSessionParameters(TypedDict):
    session_slug: str


class JoinSessionAction(ActionBase[JoinSessionParameters]):
    action_id = "circles:join"

    def get_url(self) -> str:
        slug = self.parameters.get("session_slug") or self.parameters.get("event_slug")
        if slug is None:
            raise KeyError("session_slug")
        return reverse("circles:join", kwargs={"event_slug": slug})


SubscribeActionParameters = SubscribeSpaceParameters
SubscribeAction = SubscribeSpaceAction
JoinCircleParameters = JoinSessionParameters
JoinCircleAction = JoinSessionAction


# class AttendCircleParameters(TypedDict):
#     event_slug: str


# class AttendCircleAction(ActionBase[AttendCircleParameters]):
#     action_id = "circles:event_detail"

#     def get_url(self) -> str:
#         return reverse("circles:event_detail", kwargs={"event_slug": self.parameters["event_slug"]})
