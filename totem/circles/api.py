from typing import List

from django.utils.timezone import localtime
from ninja import FilterSchema, ModelSchema, Query, Router, Schema
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


class EventsFilterSchema(FilterSchema):
    category: str | None
    author: str | None


class CategoryFilterSchema(Schema):
    name: str
    slug: str


class AuthorFilterSchema(Schema):
    name: str
    slug: str


class FilterOptionsSchema(Schema):
    categories: List[CategoryFilterSchema]
    authors: List[AuthorFilterSchema]


@router.get(
    "/",
    response={200: List[CircleEventSchema]},
    tags=["circles"],
)
@paginate
def list_circles(request, filters: EventsFilterSchema = Query()):
    return all_upcoming_recommended_events(request.user, category=filters.category, author=filters.author)


@router.get(
    "/filter-options",
    response={200: FilterOptionsSchema},
    tags=["circles"],
)
def filter_options(request):
    events = all_upcoming_recommended_events(request.user)
    # get distinct categories that have events
    categories = set(events.values_list("circle__categories__name", "circle__categories__slug").distinct())
    categories = [{"name": name, "slug": slug} for name, slug in categories]
    # get distinct authors that have events
    authors = set(events.values_list("circle__author__name", "circle__author__slug").distinct())
    authors = [{"name": name, "slug": slug} for name, slug in authors]
    return {"categories": categories, "authors": authors}
