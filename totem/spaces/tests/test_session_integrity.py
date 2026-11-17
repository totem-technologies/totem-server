import threading
import time
from collections.abc import Callable, Iterator
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.db import DatabaseError, connection, transaction
from django.db.models import QuerySet
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.email import emails
from totem.email.exceptions import EmailBounced
from totem.email.models import EmailLog
from totem.spaces.models import STARTING_REMINDER, Session, SessionException, SessionTimeConflict
from totem.spaces.rsvp import resolve_session_conflicts
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


def _row_is_locked(rows: QuerySet) -> bool:
    """Whether another connection would have to wait to lock these rows."""
    locked: list[bool] = []

    def try_lock() -> None:
        try:
            with transaction.atomic():
                list(rows.select_for_update(nowait=True))
            locked.append(False)
        except DatabaseError:
            locked.append(True)
        finally:
            connection.close()

    t = threading.Thread(target=try_lock)
    t.start()
    t.join()
    return locked[0]


def _open_session(**kwargs) -> Session:
    return SessionFactory(start=timezone.now() + timedelta(days=3), open=True, listed=True, **kwargs)


class TestRSVPSeatLimit:
    def test_seat_check_ignores_a_stale_attendee_prefetch(self, db):
        session = _open_session(seats=1)
        stale = Session.objects.prefetch_related("attendees").get(pk=session.pk)
        assert stale.seats_left() == 1

        Session.objects.get(pk=session.pk).add_attendee(UserFactory())

        with pytest.raises(SessionException):
            stale.add_attendee(UserFactory())
        assert session.attendees.count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_rsvps_cannot_overbook(self):
        session = _open_session(seats=2)
        users = [UserFactory() for _ in range(6)]
        barrier = threading.Barrier(len(users))

        def rsvp(user: User):
            try:
                instance = Session.objects.get(pk=session.pk)
                barrier.wait()
                try:
                    instance.add_attendee(user)
                except SessionException:
                    pass
            finally:
                connection.close()

        threads = [threading.Thread(target=rsvp, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert session.attendees.count() == 2


# (method name, flag it sets, start relative to now, email factory patched in models)
REMINDERS = [
    ("notify", "notified", timedelta(minutes=10), "notify_session_starting"),
    ("notify_tomorrow", "notified_tomorrow", timedelta(hours=22), "notify_session_tomorrow"),
    ("notify_missed", "notified_missed", -timedelta(hours=3), "missed_session_email"),
    ("advertise", "advertised", timedelta(days=3), "notify_session_advertisement"),
]


PUSH_FOR_EMAIL = {
    "notify_session_starting": "session_starting_notification",
    "missed_session_email": "missed_session_notification",
    "notify_session_advertisement": "session_advertisement_notification",
}


def _session_with_recipients(start_offset: timedelta, n: int = 2) -> tuple[Session, list[User]]:
    space = SpaceFactory()
    session = SessionFactory(space=space, start=timezone.now() + start_offset, open=True, listed=True)
    users = [UserFactory() for _ in range(n)]
    for user in users:
        # advertise() emails subscribers who aren't attending; the others email attendees.
        space.subscribed.add(user)
    return session, users


def _add_attendees_unless_advertising(method: str, session: Session, users: list[User]):
    if method != "advertise":
        session.attendees.add(*users)


@pytest.mark.parametrize("method,flag,start_offset,email_name", REMINDERS, ids=[r[0] for r in REMINDERS])
class TestReminderFlags:
    def test_does_not_overwrite_concurrent_edits(self, db, method, flag, start_offset, email_name):
        session, users = _session_with_recipients(start_offset)
        _add_attendees_unless_advertising(method, session, users)
        stale = Session.objects.get(pk=session.pk)

        Session.objects.filter(pk=session.pk).update(prompts_revision=5)
        getattr(stale, method)()

        session.refresh_from_db()
        assert session.prompts_revision == 5
        assert getattr(session, flag) is True

    def test_overlapping_runs_send_once(
        self, db, django_capture_on_commit_callbacks, method, flag, start_offset, email_name
    ):
        session, users = _session_with_recipients(start_offset)
        _add_attendees_unless_advertising(method, session, users)
        first = Session.objects.get(pk=session.pk)
        second = Session.objects.get(pk=session.pk)

        with django_capture_on_commit_callbacks(execute=True):
            getattr(first, method)()
        sent = len(mail.outbox)
        with django_capture_on_commit_callbacks(execute=True):
            getattr(second, method)()

        assert sent == len(users)
        assert len(mail.outbox) == sent


class TestAddAttendee:
    def test_raises_session_exception_when_the_session_is_gone(self, db):
        session = _open_session()
        Session.objects.filter(pk=session.pk).delete()
        with pytest.raises(SessionException):
            session.add_attendee(UserFactory())

    def test_email_choice_uses_the_current_session_row(self, db, django_capture_on_commit_callbacks):
        # This copy still thinks the session is days away; it now starts in minutes
        # and has already sent its starting reminders.
        stale = _open_session()
        Session.objects.filter(pk=stale.pk).update(start=timezone.now() + timedelta(minutes=5), notified=True)
        staff = UserFactory(is_staff=True)

        with django_capture_on_commit_callbacks(execute=True):
            stale.add_attendee(staff)

        assert list(EmailLog.objects.values_list("recipient", "template")) == [(staff.email, "circle_starting")]

    @pytest.mark.django_db(transaction=True)
    def test_session_row_is_not_locked_while_emailing(self):
        session = _open_session()
        locked_during_send: list[bool] = []
        real = emails.notify_session_signup

        def signup_email(target: Session, user: User):
            locked_during_send.append(_row_is_locked(Session.objects.filter(pk=session.pk)))
            return real(target, user)

        with patch("totem.spaces.models.notify_session_signup", side_effect=signup_email):
            session.add_attendee(UserFactory())

        assert locked_during_send == [False]

    @pytest.mark.parametrize("error", [ConnectionError("provider down"), ValueError("bug")])
    def test_failed_signup_email_keeps_the_rsvp(self, db, django_capture_on_commit_callbacks, error):
        session = _open_session()
        user = UserFactory()

        with (
            patch("totem.spaces.models.notify_session_signup", side_effect=error),
            patch("totem.spaces.models.capture_exception") as capture,
            django_capture_on_commit_callbacks(execute=True),
        ):
            session.add_attendee(user)

        assert session.attendees.filter(pk=user.pk).exists()
        capture.assert_called_once_with(error)

    def test_subscribes_the_attendee(self, db):
        session = _open_session()
        user = UserFactory()
        session.add_attendee(user)
        assert session.space.subscribed.filter(pk=user.pk).exists()

    def test_bounce_is_not_reported_and_changes_nothing(self, db, django_capture_on_commit_callbacks):
        session = _open_session()
        user = UserFactory()

        with (
            patch("totem.spaces.models.notify_session_signup", side_effect=EmailBounced("blocked")),
            patch("totem.spaces.models.capture_exception") as capture,
            django_capture_on_commit_callbacks(execute=True),
        ):
            session.add_attendee(user)

        capture.assert_not_called()
        assert session.attendees.filter(pk=user.pk).exists()
        assert session.space.subscribed.filter(pk=user.pk).exists()


def _record_atomic_during_send(recorded: list[bool]):
    real = emails.notify_session_signup

    def signup_email(target: Session, user: User):
        recorded.append(connection.in_atomic_block)
        return real(target, user)

    return patch("totem.spaces.models.notify_session_signup", side_effect=signup_email)


@pytest.mark.django_db(transaction=True)
class TestNoTransactionIsOpenWhileSending:
    def test_inside_a_callers_transaction(self):
        session = _open_session()
        recorded: list[bool] = []
        with _record_atomic_during_send(recorded), transaction.atomic():
            session.add_attendee(UserFactory())
        assert recorded == [False]

    def test_web_rsvp(self, client: Client):
        session = _open_session()
        client.force_login(UserFactory())
        recorded: list[bool] = []
        with _record_atomic_during_send(recorded):
            client.post(reverse("spaces:rsvp", kwargs={"session_slug": session.slug}), {"action": "add"})
        assert recorded == [False]

    def test_mobile_rsvp(self, client_with_user: tuple[Client, User]):
        session = _open_session()
        client, _ = client_with_user
        recorded: list[bool] = []
        with _record_atomic_during_send(recorded):
            response = client.post(reverse("mobile-api:rsvp_confirm", kwargs={"event_slug": session.slug}))
        assert response.status_code == 200
        assert recorded == [False]

    def test_resolve_session_conflicts(self):
        start = timezone.now() + timedelta(days=3)
        current = SessionFactory(start=start, open=True, listed=True)
        target = SessionFactory(start=start + timedelta(minutes=30), open=True, listed=True)
        user = UserFactory()
        current.attendees.add(user)
        recorded: list[bool] = []
        with _record_atomic_during_send(recorded):
            resolve_session_conflicts(target, user, [current.slug])
        assert recorded == [False]
        assert list(user.sessions_attending.all()) == [target]

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_rsvps_by_one_user_cannot_double_book(self):
        start = timezone.now() + timedelta(days=3)
        first = SessionFactory(start=start, open=True, listed=True)
        second = SessionFactory(start=start + timedelta(minutes=30), open=True, listed=True)
        user = UserFactory()
        first_added = threading.Event()
        outcome: list[str] = []

        def rsvp_first() -> None:
            try:
                with transaction.atomic():
                    Session.objects.get(pk=first.pk).add_attendee(user)
                    first_added.set()
                    # Give the other RSVP time to run its conflict check before this commits.
                    time.sleep(0.5)
            finally:
                connection.close()

        def rsvp_second() -> None:
            try:
                first_added.wait()
                Session.objects.get(pk=second.pk).add_attendee(user)
                outcome.append("added")
            except SessionTimeConflict:
                outcome.append("conflict")
            finally:
                connection.close()

        threads = [threading.Thread(target=rsvp_first), threading.Thread(target=rsvp_second)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert outcome == ["conflict"]
        assert list(user.sessions_attending.all()) == [first]


class TestResolveSessionConflicts:
    def test_seat_check_ignores_a_stale_attendee_prefetch(self, db):
        session = _open_session(seats=1)
        leaving = UserFactory()
        session.attendees.add(leaving)
        stale = Session.objects.prefetch_related("attendees").get(pk=session.pk)
        assert stale.seats_left() == 0
        session.attendees.remove(leaving)

        user = UserFactory()
        resolve_session_conflicts(stale, user, [])

        assert list(session.attendees.all()) == [user]

    @pytest.mark.django_db(transaction=True)
    def test_user_row_is_locked_before_conflicts_are_removed(self):
        start = timezone.now() + timedelta(days=3)
        current = SessionFactory(start=start, open=True, listed=True)
        target = SessionFactory(start=start + timedelta(minutes=30), open=True, listed=True)
        user = UserFactory()
        current.attendees.add(user)
        locked_during_removal: list[bool] = []
        real = Session.remove_attendee

        def remove_attendee(leaving: Session, attendee: User) -> None:
            locked_during_removal.append(_row_is_locked(User.objects.filter(pk=user.pk)))
            real(leaving, attendee)

        with patch.object(Session, "remove_attendee", autospec=True, side_effect=remove_attendee):
            resolve_session_conflicts(target, user, [current.slug])

        assert locked_during_removal == [True]
        assert list(user.sessions_attending.all()) == [target]


class TestReminderRecipients:
    @pytest.mark.django_db(transaction=True)
    def test_rsvp_committing_during_a_starting_run_gets_the_starting_email(self):
        session = _open_session()
        user = UserFactory()
        added = threading.Event()

        def rsvp() -> None:
            try:
                with transaction.atomic():
                    Session.objects.get(pk=session.pk).add_attendee(user)
                    added.set()
                    # Give the reminder run time to start before this commits.
                    time.sleep(0.3)
            finally:
                connection.close()

        t = threading.Thread(target=rsvp)
        t.start()
        added.wait()
        Session.objects.get(pk=session.pk).notify()
        t.join()

        assert EmailLog.objects.filter(recipient=user.email, template="circle_starting").exists()

    def test_flag_is_not_claimed_when_reading_recipients_fails(self, db):
        session = _open_session()

        def recipients() -> Iterator[User]:
            raise DatabaseError("db down")
            yield

        with pytest.raises(DatabaseError):
            session._send_reminders(STARTING_REMINDER, False, recipients())

        session.refresh_from_db()
        assert session.notified is False


class TestNotifyMissed:
    @pytest.mark.parametrize(
        "change",
        [{"cancelled": True}, {"start": timezone.now() + timedelta(days=1)}],
        ids=["cancelled", "not_ended"],
    )
    def test_already_notified_is_a_no_op(self, db, change):
        session = SessionFactory(**({"start": timezone.now() - timedelta(hours=3), "notified_missed": True} | change))
        session.notify_missed()


@pytest.mark.parametrize("method,flag,start_offset,email_name", REMINDERS, ids=[r[0] for r in REMINDERS])
class TestRemindersAreSentAtMostOnce:
    def test_failed_recipients_are_not_retried(
        self, db, django_capture_on_commit_callbacks, method, flag, start_offset, email_name
    ):
        session, users = _session_with_recipients(start_offset)
        _add_attendees_unless_advertising(method, session, users)
        real: Callable = getattr(emails, email_name)

        def flaky(session: Session, user: User, *args, **kwargs):
            if user == users[0]:
                raise ConnectionError("timed out")
            return real(session, user, *args, **kwargs)

        with (
            patch(f"totem.spaces.models.{email_name}", side_effect=flaky),
            patch("totem.spaces.models.capture_exception"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            getattr(session, method)()
        with django_capture_on_commit_callbacks(execute=True):
            getattr(Session.objects.get(pk=session.pk), method)()

        assert [m.to[0] for m in mail.outbox] == [users[1].email]
        session.refresh_from_db()
        assert getattr(session, flag) is True

    def test_total_outage_keeps_the_flag(
        self, db, django_capture_on_commit_callbacks, method, flag, start_offset, email_name
    ):
        session, users = _session_with_recipients(start_offset)
        _add_attendees_unless_advertising(method, session, users)

        with (
            patch(f"totem.spaces.models.{email_name}", side_effect=ConnectionError("provider down")),
            patch("totem.spaces.models.capture_exception") as capture,
            django_capture_on_commit_callbacks(execute=True),
        ):
            getattr(session, method)()

        assert capture.call_count == len(users)
        session.refresh_from_db()
        assert getattr(session, flag) is True

    def test_any_error_for_one_recipient_does_not_stop_the_rest(
        self, db, django_capture_on_commit_callbacks, method, flag, start_offset, email_name
    ):
        session, users = _session_with_recipients(start_offset, n=3)
        _add_attendees_unless_advertising(method, session, users)
        real: Callable = getattr(emails, email_name)

        def broken_template(session: Session, user: User, *args, **kwargs):
            if user == users[0]:
                raise ValueError("template error")
            return real(session, user, *args, **kwargs)

        with (
            patch(f"totem.spaces.models.{email_name}", side_effect=broken_template),
            patch("totem.spaces.models.capture_exception") as capture,
            django_capture_on_commit_callbacks(execute=True),
        ):
            getattr(session, method)()

        assert sorted(m.to[0] for m in mail.outbox) == sorted(u.email for u in users[1:])
        capture.assert_called_once()

    def test_bounce_is_not_reported_and_changes_nothing(
        self, db, django_capture_on_commit_callbacks, method, flag, start_offset, email_name
    ):
        session, users = _session_with_recipients(start_offset, n=1)
        _add_attendees_unless_advertising(method, session, users)
        attending_before = set(session.attendees.all())

        with (
            patch(f"totem.spaces.models.{email_name}", side_effect=EmailBounced("blocked")),
            patch("totem.spaces.models.capture_exception") as capture,
            django_capture_on_commit_callbacks(execute=True),
        ):
            getattr(session, method)()

        capture.assert_not_called()
        assert set(session.attendees.all()) == attending_before
        assert session.space.subscribed.filter(pk=users[0].pk).exists()

    def test_push_still_reaches_a_flagged_user(
        self, db, django_capture_on_commit_callbacks, method, flag, start_offset, email_name
    ):
        session, users = _session_with_recipients(start_offset, n=1)
        _add_attendees_unless_advertising(method, session, users)
        User.objects.filter(pk=users[0].pk).update(email_bounced_at=timezone.now())
        push_name = PUSH_FOR_EMAIL.get(email_name)
        if push_name is None:
            pytest.skip("this reminder has no push notification")

        with (
            patch(f"totem.spaces.models.{push_name}") as push,
            django_capture_on_commit_callbacks(execute=True),
        ):
            getattr(session, method)()

        assert mail.outbox == []
        push.assert_called_once()

    def test_database_errors_claiming_the_flag_propagate(self, db, method, flag, start_offset, email_name):
        session, users = _session_with_recipients(start_offset)
        _add_attendees_unless_advertising(method, session, users)

        with (
            patch.object(Session, "_claim_notification", side_effect=DatabaseError("db down")),
            pytest.raises(DatabaseError),
        ):
            getattr(session, method)()


class TestAdvertise:
    def test_queries_do_not_scale_with_subscribers(self, db, django_assert_max_num_queries):
        session, users = _session_with_recipients(timedelta(days=3), n=1)
        with patch("totem.spaces.models.send_session_notice"):
            session.advertise(force=True)
            for _ in range(10):
                session.space.subscribed.add(UserFactory())
            with django_assert_max_num_queries(8):
                session.advertise(force=True)
