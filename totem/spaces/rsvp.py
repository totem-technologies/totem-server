from django.db import transaction

from totem.users.models import User

from .models import Session, SessionTimeConflict


def resolve_session_conflicts(
    session: Session,
    user: User,
    conflicting_session_slugs: list[str],
) -> None:
    """Atomically replace the user's current conflicts with ``session``.

    Submitted slugs are treated as the conflicts the user consented to leave.
    If another conflict exists by the time this runs, callers receive a fresh
    ``SessionTimeConflict`` and can ask the user to confirm again.
    """
    with transaction.atomic():
        # Same lock order as Session.add_attendee (user row, then session rows), taken
        # before any attendance changes so concurrent RSVPs by this user queue up.
        User.objects.select_for_update(no_key=True).get(pk=user.pk)
        submitted_slugs = set(conflicting_session_slugs)
        submitted_sessions = {
            item.slug: item
            for item in Session.objects.visible_to(user)
            .filter(slug__in=submitted_slugs, attendees=user)
            .overlapping(session)
            .select_related("space__author")
            .prefetch_related("attendees")
        }

        detected_conflicts = list(Session.objects.time_conflicts_for(session, user)) if not user.is_staff else []
        current_conflict_slugs = [conflict.slug for conflict in detected_conflicts]
        if set(current_conflict_slugs) - submitted_slugs:
            raise SessionTimeConflict(detected_conflicts)

        for conflict_slug in current_conflict_slugs:
            submitted_sessions[conflict_slug].remove_attendee(user)
        session.add_attendee(user, check_time_conflicts=False)
