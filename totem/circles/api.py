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


# class EventsFilterSchema(FilterSchema):
#     category: str | None = None
#     author: str | None = None


# class FilterOptionsSchema(Schema):
#     categories: List[str]
#     authors: List[str]


@router.get(
    "/",
    response={200: List[CircleEventSchema]},
    tags=["circles"],
)
@paginate
def list_circles(request):
    return all_upcoming_recommended_events(request.user)
    # return filters.filter(all_upcoming_recommended_events(request.user))


# @router.get(
#     "/filter-options",
#     response={200: FilterOptionsSchema},
#     tags=["circles"],
# )
# def filter_options(request):
#     return {
#         "categories": Circle.objects.values_list("categories__slug", flat=True).distinct(),
#         "authors": Circle.objects.values_list("author__username", flat=True).distinct(),
#     }
