"""Read-only session history for a single user, shown in the User admin.

Admins use this when looking into bans, no-shows, or which Keepers someone
keeps signing up with. It's built from the attendees/joined many-to-many
fields, so a signup that was later withdrawn leaves no trace here.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from django.db.models import Q

from totem.users.models import User

from .models import Session, SessionFeedback


class SessionStatus(StrEnum):
    ATTENDED = "Attended"
    NO_SHOW = "No-show"
    CANCELLED = "Cancelled"
    IN_PROGRESS = "In progress"
    UPCOMING = "Upcoming"


@dataclass(frozen=True)
class SessionHistoryEntry:
    session: Session
    signed_up: bool
    joined: bool
    #: Banned from this session's room.
    banned: bool
    feedback: SessionFeedback | None

    @property
    def status(self) -> SessionStatus:
        if self.joined:
            return SessionStatus.ATTENDED
        if self.session.cancelled:
            return SessionStatus.CANCELLED
        if not self.session.started():
            return SessionStatus.UPCOMING
        if not self.session.ended():
            return SessionStatus.IN_PROGRESS
        return SessionStatus.NO_SHOW


@dataclass(frozen=True)
class KeeperSummary:
    keeper: User
    attended: int
    no_shows: int
    cancelled: int
    #: Upcoming or in progress.
    upcoming: int

    @property
    def total(self) -> int:
        return self.attended + self.no_shows + self.cancelled + self.upcoming


@dataclass(frozen=True)
class SessionHistory:
    #: Newest first.
    entries: list[SessionHistoryEntry]
    #: Keepers with the most sessions first.
    keepers: list[KeeperSummary]

    @property
    def attended(self) -> int:
        return sum(entry.status == SessionStatus.ATTENDED for entry in self.entries)

    @property
    def no_shows(self) -> int:
        return sum(entry.status == SessionStatus.NO_SHOW for entry in self.entries)

    @property
    def attendance_percent(self) -> int:
        """Share of sessions that took place that this person showed up to."""
        held = self.attended + self.no_shows
        if not held:
            return 0
        return round(100 * self.attended / held)


def session_history(user: User) -> SessionHistory:
    sessions = (
        Session.objects.filter(Q(attendees=user) | Q(joined=user))
        .distinct()
        .select_related("space__author", "room")
        .order_by("-start")
    )
    signed_up = set(user.sessions_attending.values_list("pk", flat=True))
    joined = set(user.sessions_joined.values_list("pk", flat=True))
    feedback = {f.session_id: f for f in SessionFeedback.objects.filter(user=user)}

    entries: list[SessionHistoryEntry] = []
    for session in sessions:
        room = getattr(session, "room", None)
        entries.append(
            SessionHistoryEntry(
                session=session,
                signed_up=session.pk in signed_up,
                joined=session.pk in joined,
                banned=room is not None and user.slug in room.banned_participants,
                feedback=feedback.get(session.pk),
            )
        )

    return SessionHistory(entries=entries, keepers=_keeper_summaries(entries))


def _keeper_summaries(entries: list[SessionHistoryEntry]) -> list[KeeperSummary]:
    keepers: dict[int, User] = {}
    counts: dict[int, dict[SessionStatus, int]] = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        keeper = entry.session.space.author
        keepers[keeper.pk] = keeper
        counts[keeper.pk][entry.status] += 1

    summaries = [
        KeeperSummary(
            keeper=keeper,
            attended=counts[pk][SessionStatus.ATTENDED],
            no_shows=counts[pk][SessionStatus.NO_SHOW],
            cancelled=counts[pk][SessionStatus.CANCELLED],
            upcoming=counts[pk][SessionStatus.UPCOMING] + counts[pk][SessionStatus.IN_PROGRESS],
        )
        for pk, keeper in keepers.items()
    ]
    return sorted(summaries, key=lambda s: (-s.total, s.keeper.name or s.keeper.email))
