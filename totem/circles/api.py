from typing import List

from django.utils.timezone import localtime
from ninja import ModelSchema, Router
from ninja.pagination import paginate

from totem.users.schemas import UserSchema

from .filters import all_upcoming_recommended_events
from .models import Circle, CircleEvent

router = Router()


class CircleSchema(ModelSchema):
    author: UserSchema

    class Meta:
        model = Circle
        fields = ["title", "slug", "date_created", "date_modified"]


class CircleEventSchema(ModelSchema):
    circle: CircleSchema
    url: str

    @staticmethod
    def resolve_start(obj: CircleEvent):
        return localtime(obj.start)

    @staticmethod
    def resolve_url(obj: CircleEvent):
        return obj.get_absolute_url()

    class Meta:
        model = CircleEvent
        fields = ["start", "slug", "date_created", "date_modified", "circle"]


@router.get(
    "/",
    response={200: List[CircleEventSchema]},
    tags=["circles"],
)
@paginate
def list_circles(request, category: str | None = None):
    return all_upcoming_recommended_events(request.user, category=category)
