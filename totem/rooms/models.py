from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.postgres.fields import ArrayField
from django.db import models

from totem.utils.models import BaseModel

from .schemas import RoomState, RoomStatus, TurnState

if TYPE_CHECKING:
    from totem.spaces.models import Session


class RoomQuerySet(models.QuerySet["Room"]):
    def for_session(self, session_slug: str) -> RoomQuerySet:
        return self.select_related("session").filter(session__slug=session_slug)

    def get_or_create_for_session(self, session: Session) -> Room:
        """Get or create a Room for a Session, initializing from Session data."""
        room, created = self.get_or_create(
            session=session,
            defaults={
                "keeper": session.space.author.slug,
                "talking_order": [a.slug for a in session.attendees.all()],
            },
        )
        return room


RoomManager = models.Manager.from_queryset(RoomQuerySet)


class Room(BaseModel):
    """
    Real-time room state. This is the ephemeral state machine row,
    not the Session model that tracks signups, title, etc.

    User references are stored as slugs (short public IDs) rather than
    FKs, since this is transient state and we don't need referential integrity.

    current_speaker and next_speaker are null only when the room is not active
    (lobby or ended). While active, both are always set — if there's only one
    participant, they can be the same person.
    """

    objects = RoomManager()

    session = models.OneToOneField(
        "spaces.Session",
        on_delete=models.CASCADE,
        related_name="room",
    )
    status = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in RoomStatus],
        default=RoomStatus.WAITING_ROOM,
    )
    turn_state = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in TurnState],
        default=TurnState.IDLE,
    )
    keeper = models.CharField(max_length=50)  # user slug
    current_speaker = models.CharField(max_length=50, null=True)  # user slug
    next_speaker = models.CharField(max_length=50, null=True)  # user slug
    talking_order = ArrayField(models.CharField(max_length=50), default=list)  # user slugs
    state_version = models.PositiveIntegerField(default=0)

    def to_state(self) -> RoomState:
        return RoomState(
            session_slug=self.session.slug,
            version=self.state_version,
            status=RoomStatus(self.status),
            turn_state=TurnState(self.turn_state),
            current_speaker=self.current_speaker,
            next_speaker=self.next_speaker,
            talking_order=self.talking_order,
            keeper=self.keeper,
        )


class RoomEventLog(BaseModel):
    """Append-only log of every state transition."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="events")
    version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=50)
    actor = models.CharField(max_length=50)  # user slug
    snapshot = models.JSONField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        ordering = ["version"]
