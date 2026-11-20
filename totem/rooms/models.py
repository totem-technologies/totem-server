from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from totem.utils.models import BaseModel

from .schemas import (
    ActiveDetail,
    EndedDetail,
    EndReason,
    RoomState,
    RoomStatus,
    StatusDetail,
    TurnState,
    WaitingRoomDetail,
)

if TYPE_CHECKING:
    from totem.spaces.models import Session, SessionRound


class RoomManager(models.Manager["Room"]):
    def for_session(self, session_slug: str) -> models.QuerySet[Room]:
        return self.select_related("session").filter(session__slug=session_slug)

    def get_or_create_for_session(self, session: Session) -> Room:
        """Get or create a Room for a Session, initializing from Session data."""
        room, _created = self.get_or_create(
            session=session,
            defaults={
                "keeper": session.space.author.slug,
                "talking_order": []
                if settings.SERVER_ENFORCED_ADMISSION
                else [a.slug for a in session.attendees.all()],
            },
        )
        return room


class Room(BaseModel):
    """
    Real-time room state. This is the ephemeral state machine row,
    not the Session model that tracks signups, title, etc.

    User references are stored as slugs (short public IDs) rather than
    FKs, since this is transient state and we don't need referential integrity.

    With enforced admission, an active room can temporarily have no speaker
    assignments when no eligible activated participant can hold a turn. Valid
    disconnected assignments/order are retained; pending users are never used
    to fill gaps. A solo eligible participant can hold both assignments.
    """

    objects: ClassVar[RoomManager] = RoomManager()  # type: ignore[assignment]

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
    banned_participants = ArrayField(models.CharField(max_length=50), default=list)  # user slugs
    round_number = models.PositiveIntegerField(default=0)
    state_version = models.PositiveIntegerField(default=0)
    approval_required = models.BooleanField(default=True)
    admission_revision = models.PositiveIntegerField(default=0)
    admission_version = models.PositiveIntegerField(default=0)
    end_reason = models.CharField(
        max_length=20,
        choices=[(r.value, r.value) for r in EndReason],
        null=True,
        default=None,
    )

    def _build_status_detail(self) -> StatusDetail:
        match self.status:
            case RoomStatus.ENDED:
                return EndedDetail(reason=EndReason(self.end_reason))
            case RoomStatus.ACTIVE:
                return ActiveDetail()
            case _:
                return WaitingRoomDetail()

    def _session_round(self) -> SessionRound | None:
        from totem.spaces.models import SessionRound

        return SessionRound.objects.filter(session_id=self.session_id, number=self.round_number).first()

    @property
    def round_message(self) -> str | None:
        round = self._session_round()
        return round.prompt or None if round else None

    def to_state(self) -> RoomState:
        round = self._session_round()
        return RoomState(
            session_slug=self.session.slug,
            version=self.state_version,
            status=RoomStatus(self.status),
            turn_state=TurnState(self.turn_state),
            status_detail=self._build_status_detail(),
            current_speaker=self.current_speaker,
            next_speaker=self.next_speaker,
            talking_order=self.talking_order,
            keeper=self.keeper,
            banned_participants=self.banned_participants,
            round_number=self.round_number,
            round_message=round.prompt or None if round else None,
            round_prompt_id=round.prepared_prompt_id if round else None,
        )


class AdmissionState(models.TextChoices):
    NONE = "none"
    ADMITTED = "admitted"
    PERMANENTLY_DECLINED = "permanently_declined"
    REVOKED = "revoked"


class SessionAdmission(BaseModel):
    """Durable authorization, independent of any connection or Keeper device."""

    session = models.ForeignKey("spaces.Session", on_delete=models.CASCADE, related_name="admissions")
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="session_admissions")
    state = models.CharField(max_length=24, choices=AdmissionState.choices, default=AdmissionState.NONE)
    version = models.PositiveIntegerField(default=0)
    decision_actor = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, related_name="+")
    decided_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "user"], name="unique_session_admission"),
            models.CheckConstraint(condition=models.Q(state__in=AdmissionState.values), name="valid_admission_state"),
        ]


class AttemptStatus(models.TextChoices):
    PENDING = "pending"
    GRANTING = "granting"
    ADMITTED = "admitted"
    DECLINED = "declined"
    PERMANENTLY_DECLINED = "permanently_declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    FAILED = "failed"


class AdmissionAttempt(BaseModel):
    """One idempotent request/connection attempt; terminal attempts never reopen."""

    admission = models.ForeignKey(SessionAdmission, on_delete=models.CASCADE, related_name="attempts")
    request_id = models.UUIDField(unique=True)
    attempt_id = models.UUIDField(unique=True)
    status = models.CharField(max_length=24, choices=AttemptStatus.choices, default=AttemptStatus.PENDING)
    version = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    decision_actor = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, related_name="+")
    decided_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    connected_at = models.DateTimeField(null=True)
    participant_sid = models.CharField(max_length=64, blank=True)
    token_expires_at = models.DateTimeField(null=True)
    returning = models.BooleanField(default=False)
    session_started = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["admission"],
                condition=models.Q(status__in=["pending", "granting"]),
                name="one_active_admission_attempt",
            ),
            models.CheckConstraint(condition=models.Q(status__in=AttemptStatus.values), name="valid_attempt_status"),
        ]
        indexes = [models.Index(fields=["status", "expires_at"], name="admission_attempt_expiry")]


class AdmissionPermissionSync(BaseModel):
    """Durable permission reconciliation journal; network calls never hold DB locks."""

    admission = models.OneToOneField(SessionAdmission, on_delete=models.CASCADE, related_name="permission_sync")
    revision = models.PositiveIntegerField(default=0)
    desired_admitted = models.BooleanField(default=False)
    authority_keeper = models.CharField(max_length=50, blank=True)
    applied_revision = models.PositiveIntegerField(null=True)
    participant_sid = models.CharField(max_length=64, blank=True)
    operation_id = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    checked_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=32, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True)


class AdmissionCommand(BaseModel):
    """Idempotency receipt, never replayed as authorization or a permission grant."""

    session = models.ForeignKey("spaces.Session", on_delete=models.CASCADE, related_name="admission_commands")
    command_id = models.UUIDField()
    actor = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="+")
    action = models.CharField(max_length=24)
    payload_hash = models.CharField(max_length=64)
    result = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "command_id"], name="unique_session_admission_command"),
        ]


class RoomEventLog(BaseModel):
    """Append-only log of every state transition."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="events")
    version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=50)
    actor = models.CharField(max_length=50)  # user slug
    snapshot = models.JSONField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        ordering = ["version"]
