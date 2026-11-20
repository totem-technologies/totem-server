"""Versioned refresh hints. Database snapshots, never packets, are authority."""

from __future__ import annotations

import logging
from functools import partial

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..livekit import publish_admission_changed
from ..models import Room

logger = logging.getLogger(__name__)


def bump_admission_version(session_id: int, identity: str | None = None, *, notify: bool = True) -> None:
    """Caller holds the Session lock; notifications are sent only after commit."""
    Room.objects.filter(session_id=session_id).update(
        admission_version=F("admission_version") + 1, date_modified=timezone.now()
    )
    if notify:
        transaction.on_commit(partial(_notify, session_id, identity))


def _notify(session_id: int, identity: str | None) -> None:
    room = Room.objects.select_related("session").filter(session_id=session_id).first()
    if not room:
        return
    destinations = [room.keeper]
    if identity:
        destinations.append(identity)
    try:
        publish_admission_changed(room.session.slug, room.admission_version, destinations)
    except Exception:
        # A missed event never rolls back a committed admission decision.
        logger.exception("Admission refresh notification failed for %s", room.session.slug)
