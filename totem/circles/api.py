from typing import List

from django.utils.timezone import localtime
from ninja import ModelSchema, Router
from ninja.pagination import paginate
from pydantic import field_validator

from .filters import all_upcoming_recommended_events
from .models import Circle, CircleEvent

router = Router()


class CircleSchema(ModelSchema):
    class Meta:
        model = Circle
        fields = ["title", "slug", "date_created", "date_modified"]


class CircleEventSchema(ModelSchema):
    circle: CircleSchema

    @field_validator("start", check_fields=False)
    def convert_to_localtime(cls, value):
        return localtime(value)

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
