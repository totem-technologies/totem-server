from typing import List

from ninja import Router

from .models import Series
from .schemas import SeriesListSchema, SeriesSchema

router = Router(tags=["Series"])


@router.get("", response=List[SeriesListSchema], summary="List all published Series")
def list_series(request):
    """
    Returns a list of all published Series, optimized for list view.
    """
    series = (
        Series.objects.filter(published=True)
        .select_related("author")
        .prefetch_related("categories", "events")
        .order_by("-created")
    )
    return series


@router.get("/{slug}", response=SeriesSchema, summary="Get a single Series by slug")
def get_series(request, slug: str):
    """
    Retrieve a single Series by its unique slug.
    This endpoint provides the full details of the series, including all its events.
    """
    series = (
        Series.objects.filter(published=True)
        .select_related("author")
        .prefetch_related("categories", "events")
        .get(slug=slug)
    )
    return series
