from typing import TypedDict

from django.urls import reverse

from totem.users.actions_base import ActionBase


class SubscribeActionParameters(TypedDict):
    circle_slug: str
    subscribe: bool


class SubscribeAction(ActionBase[SubscribeActionParameters]):
    action_id = "circles:subscribe"

    def get_url(self):
        return reverse(self.action_id, kwargs={"slug": self.parameters["circle_slug"]})


class JoinCircleParameters(TypedDict):
    event_slug: str


class JoinCircleAction(ActionBase[JoinCircleParameters]):
    action_id = "circles:join"

    def get_url(self) -> str:
        return reverse("circles:join", kwargs={"event_slug": self.parameters["event_slug"]})


# class AttendCircleParameters(TypedDict):
#     event_slug: str


# class AttendCircleAction(ActionBase[AttendCircleParameters]):
#     action_id = "circles:event_detail"

#     def get_url(self) -> str:
#         return reverse("circles:event_detail", kwargs={"event_slug": self.parameters["event_slug"]})
