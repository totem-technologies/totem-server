from typing import List

from ninja import ModelSchema, Router

from .models import Circle, CircleEvent

router = Router()


class CircleSchema(ModelSchema):
    class Meta:
        model = Circle
        fields = ["title", "slug", "date_created", "date_modified"]


class CircleEventSchema(ModelSchema):
    circle: CircleSchema

    class Meta:
        model = CircleEvent
        fields = ["start", "slug", "date_created", "date_modified", "circle"]


@router.get(
    "/",
    response={200: List[CircleEventSchema]},
    tags=["circles"],
)
def list_circles(request):
    # return [CircleEvent.objects.all()]
    return []
