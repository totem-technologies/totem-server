from typing import List

from ninja import ModelSchema

from totem.users.schemas import UserSchema

from .models import Series, SeriesCategory, SeriesEvent


class SeriesCategorySchema(ModelSchema):
    class Meta:
        model = SeriesCategory
        fields = ["name", "slug"]


class SeriesEventSchema(ModelSchema):
    class Meta:
        model = SeriesEvent
        fields = ["slug", "title", "start", "duration_minutes", "order"]


class SeriesSchema(ModelSchema):
    author: UserSchema
    categories: List[SeriesCategorySchema]
    events: List[SeriesEventSchema]

    class Meta:
        model = Series
        fields = [
            "slug",
            "title",
            "subtitle",
            "image",
            "short_description",
            "content",
            "published",
        ]


class SeriesListSchema(ModelSchema):
    author: UserSchema
    categories: List[SeriesCategorySchema]
    next_event: SeriesEventSchema | None

    class Meta:
        model = Series
        fields = [
            "slug",
            "title",
            "subtitle",
            "image",
            "short_description",
        ]

    @staticmethod
    def resolve_next_event(obj: Series):
        return obj.next_event()
