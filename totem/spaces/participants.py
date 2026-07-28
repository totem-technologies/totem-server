"""Read-only participant insights for the Session admin.

Keepers and admins use this to see who is signed up for a Session and how
reliably they've shown up in the past, without digging through the raw
attendee/joined many-to-many fields.
"""

from dataclasses import dataclass

from django.db.models import Count, Q
from django.utils import timezone

from totem.rooms.models import Room
from totem.users.models import User

from .models import Session


@dataclass(frozen=True)
class ParticipantInsight:
    pk: int
    slug: str
    name: str
    email: str
    #: Earlier sessions this person signed up for, excluding cancelled ones.
    rsvps: int
    #: Earlier sessions this person actually joined.
    attended: int
    #: Banned from some other session.
    banned: bool
    joined_this_session: bool

    @property
    def attendance_percent(self) -> int:
        if not self.rsvps:
            return 0
        return round(100 * self.attended / self.rsvps)

    @property
    def first_time(self) -> bool:
        """Never joined a Space. A no-show RSVP doesn't count as attending."""
        return self.attended == 0


def _globally_banned_slugs(slugs: list[str]) -> set[str]:
    """Which of these users are banned from any session's room, anywhere."""
    if not slugs:
        return set()
    banned_lists = Room.objects.filter(banned_participants__overlap=slugs).values_list("banned_participants", flat=True)
    return {slug for banned in banned_lists for slug in banned} & set(slugs)


def participant_insights(session: Session) -> list[ParticipantInsight]:
    now = timezone.now()

    def history(relation: str) -> Q:
        """Sessions that count towards a person's record: earlier than this one,
        and not cancelled. A session is never part of its own history, or a
        first-timer would lose the badge the moment they joined."""
        return Q(**{f"{relation}__start__lt": now, f"{relation}__cancelled": False}) & ~Q(
            **{f"{relation}__pk": session.pk}
        )

    # Select by pk rather than annotating session.attendees directly: filtering on
    # sessions_attending would make the annotation reuse that same (session-scoped) join.
    attendee_ids = list(session.attendees.values_list("pk", flat=True))
    rows = list(
        User.objects.filter(pk__in=attendee_ids)
        .annotate(
            rsvp_count=Count("sessions_attending", filter=history("sessions_attending"), distinct=True),
            attended_count=Count("sessions_joined", filter=history("sessions_joined"), distinct=True),
        )
        .order_by("name", "email")
        .values("pk", "slug", "name", "email", "rsvp_count", "attended_count")
    )
    banned = _globally_banned_slugs([row["slug"] for row in rows])
    joined = set(session.joined.values_list("slug", flat=True))
    return [
        ParticipantInsight(
            pk=row["pk"],
            slug=row["slug"],
            name=row["name"],
            email=row["email"],
            # Someone can be dropped from attendees after the fact, so a join with no
            # RSVP is possible. Count it as a signup rather than report 1 out of 0.
            rsvps=max(row["rsvp_count"], row["attended_count"]),
            attended=row["attended_count"],
            banned=row["slug"] in banned,
            joined_this_session=row["slug"] in joined,
        )
        for row in rows
    ]
