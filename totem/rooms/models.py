from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from .schemas import RoomState, RoomStatus, TurnState


class Room(models.Model):
    """
    Real-time room state. This is the ephemeral state machine row,
    not the Session model that tracks signups, title, etc.

    User references are stored as slugs (short public IDs) rather than
    FKs, since this is transient state and we don't need referential integrity.

    current_speaker and next_speaker are null only when the room is not active
    (lobby or ended). While active, both are always set — if there's only one
    participant, they can be the same person.
    """

    session = models.OneToOneField(
        "spaces.Session",
        on_delete=models.CASCADE,
        related_name="room",
    )
    status = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in RoomStatus],
        default=RoomStatus.LOBBY,
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def to_state(self) -> RoomState:
        return RoomState(
            room_id=self.session.slug,
            version=self.state_version,
            status=RoomStatus(self.status),
            turn_state=TurnState(self.turn_state),
            current_speaker=self.current_speaker,
            next_speaker=self.next_speaker,
            talking_order=self.talking_order,
            keeper=self.keeper,
        )

    class Meta:
        app_label = "rooms"


class RoomEventLog(models.Model):
    """Append-only log of every state transition."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="events")
    version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=50)
    actor = models.CharField(max_length=50)  # user slug
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "rooms"
        ordering = ["version"]
