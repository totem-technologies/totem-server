from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from totem.meetings.tasks import end_sessions_without_keeper
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.tests.factories import UserFactory


@patch("totem.meetings.tasks.end_room")
@patch("totem.meetings.tasks.is_user_in_room", return_value=False)
class TestEndSessionsWithoutKeeper:
    def test_no_sessions_to_end(self, mock_livekit, mock_end_room, db):
        """No sessions should be ended when none exist."""
        assert end_sessions_without_keeper() == 0
        mock_end_room.assert_not_called()

    def test_session_not_started_yet(self, mock_livekit, mock_end_room, db):
        """Sessions that haven't started should not be ended."""
        SessionFactory(start=timezone.now() + timedelta(minutes=10))
        assert end_sessions_without_keeper() == 0

    def test_session_within_grace_period(self, mock_livekit, mock_end_room, db):
        """Sessions within the 5-minute grace period should not be ended."""
        SessionFactory(start=timezone.now() - timedelta(minutes=3))
        assert end_sessions_without_keeper() == 0

    def test_session_ended_without_keeper(self, mock_livekit, mock_end_room, db):
        """Sessions where keeper hasn't joined after 5 minutes should be ended."""
        author = UserFactory()
        space = SpaceFactory(author=author)
        session = SessionFactory(
            space=space,
            start=timezone.now() - timedelta(minutes=10),
        )
        assert session.ended_at is None
        assert end_sessions_without_keeper() == 1
        session.refresh_from_db()
        assert session.ended_at is not None
        mock_end_room.assert_called_once_with(session.slug)

    def test_session_not_ended_when_keeper_joined_db(self, mock_livekit, mock_end_room, db):
        """Sessions where keeper has joined (in DB) should not be ended."""
        author = UserFactory()
        space = SpaceFactory(author=author)
        session = SessionFactory(
            space=space,
            start=timezone.now() - timedelta(minutes=10),
        )
        session.joined.add(author)
        session.save()
        assert end_sessions_without_keeper() == 0
        session.refresh_from_db()
        assert session.ended_at is None
        mock_livekit.assert_not_called()
        mock_end_room.assert_not_called()

    def test_session_not_ended_when_keeper_in_livekit(self, mock_livekit, mock_end_room, db):
        """Sessions where keeper is in LiveKit room should not be ended."""
        mock_livekit.return_value = True
        author = UserFactory()
        space = SpaceFactory(author=author)
        session = SessionFactory(
            space=space,
            start=timezone.now() - timedelta(minutes=10),
        )
        assert end_sessions_without_keeper() == 0
        session.refresh_from_db()
        assert session.ended_at is None
        mock_end_room.assert_not_called()

    def test_already_ended_session_not_processed(self, mock_livekit, mock_end_room, db):
        """Sessions already ended should not be processed again."""
        author = UserFactory()
        space = SpaceFactory(author=author)
        ended_time = timezone.now() - timedelta(minutes=5)
        session = SessionFactory(
            space=space,
            start=timezone.now() - timedelta(minutes=10),
            ended_at=ended_time,
        )
        assert end_sessions_without_keeper() == 0
        session.refresh_from_db()
        assert session.ended_at == ended_time

    def test_cancelled_session_not_processed(self, mock_livekit, mock_end_room, db):
        """Cancelled sessions should not be processed."""
        author = UserFactory()
        space = SpaceFactory(author=author)
        session = SessionFactory(
            space=space,
            start=timezone.now() - timedelta(minutes=10),
            cancelled=True,
        )
        assert end_sessions_without_keeper() == 0
        session.refresh_from_db()
        assert session.ended_at is None

    def test_old_session_not_processed(self, mock_livekit, mock_end_room, db):
        """Sessions older than 1 hour should not be processed."""
        author = UserFactory()
        space = SpaceFactory(author=author)
        session = SessionFactory(
            space=space,
            start=timezone.now() - timedelta(hours=2),
        )
        assert end_sessions_without_keeper() == 0
        session.refresh_from_db()
        assert session.ended_at is None

    def test_multiple_sessions_processed(self, mock_livekit, mock_end_room, db):
        """Multiple sessions should be processed correctly."""
        author1 = UserFactory()
        author2 = UserFactory()
        space1 = SpaceFactory(author=author1)
        space2 = SpaceFactory(author=author2)

        session1 = SessionFactory(
            space=space1,
            start=timezone.now() - timedelta(minutes=10),
        )

        session2 = SessionFactory(
            space=space2,
            start=timezone.now() - timedelta(minutes=10),
        )
        session2.joined.add(author2)
        session2.save()

        assert end_sessions_without_keeper() == 1
        session1.refresh_from_db()
        session2.refresh_from_db()
        assert session1.ended_at is not None
        assert session2.ended_at is None

    def test_handles_end_room_errors_gracefully(self, mock_livekit, mock_end_room, db):
        """Session should still be ended in DB even if LiveKit end_room fails."""
        from totem.meetings.livekit_provider import RoomNotFoundError

        mock_end_room.side_effect = RoomNotFoundError("Room not found")
        author = UserFactory()
        space = SpaceFactory(author=author)
        session = SessionFactory(
            space=space,
            start=timezone.now() - timedelta(minutes=10),
        )
        assert end_sessions_without_keeper() == 1
        session.refresh_from_db()
        assert session.ended_at is not None
