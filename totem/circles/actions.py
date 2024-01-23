from dataclasses import dataclass

from django.urls import reverse

from totem.users.actions import ActionBase


@dataclass
class SubscribeActionParameters:
    circle_slug: str
    subscribe: bool


class SubscribeAction(ActionBase[SubscribeActionParameters]):
    action_id = "circles:subscribe"
    __parameters_type__ = SubscribeActionParameters

    @classmethod
    def get_url(cls, parameters):
        return reverse(cls.action_id, kwargs={"slug": parameters.circle_slug})
