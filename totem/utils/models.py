import random
import string
from typing import Any
from uuid import uuid4

from django.db import models
from django.db.models.options import Options
from django.urls import reverse


def make_slug():
    random.seed(str(uuid4()))
    return "".join(
        random.sample(string.ascii_lowercase, 3)
        + random.sample(string.digits, 3)
        + random.sample(string.ascii_lowercase, 3)
    )


class PeersManager(models.Manager):
    """Default queryset to FETCH_PEERS: when one instance touches an unloaded
    relation or deferred field, Django fetches it for every instance from the
    same queryset. A forgotten select_related costs two queries, not N+1.
    Many-to-many access and .count() are not covered; prefetch those."""

    def get_queryset(self):
        return super().get_queryset().fetch_mode(models.FETCH_PEERS)


class BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AdminURLMixin:
    _meta: Options
    pk: Any

    def get_admin_url(self):
        return reverse(f"admin:{self._meta.app_label}_{self._meta.model_name}_change", args=(self.pk,))


class SluggedModel(BaseModel):
    slug = models.SlugField(db_index=True, unique=True, editable=False, blank=True, default=make_slug)

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        abstract = True
