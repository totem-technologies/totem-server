from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from totem.rooms.livekit import LiveKitConfigurationError, ParticipantNotFoundError
from totem.rooms.models import Room
from totem.spaces.tests.factories import SessionFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


def _post_event(client: Client, session_slug: str, event: dict, version: int):
    return client.post(
        f"/api/mobile/protected/rooms/{session_slug}/event",
        data={"event": event, "last_seen_version": version},
        content_type="application/json",
    )


def _get_state(client: Client, session_slug: str):
    return client.get(f"/api/mobile/protected/rooms/{session_slug}/state")


@pytest.mark.django_db
class TestPostEvent:
    def test_start_room(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            resp = _post_event(client, session.slug, {"type": "start_room"}, 0)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["current_speaker"] == user.slug
        assert data["version"] == 1

    def test_full_pass_accept_cycle(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        user1 = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user1)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        connected = {keeper.slug, user1.slug}

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value=connected,
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            # Start
            resp = _post_event(client, session.slug, {"type": "start_room"}, 0)
            assert resp.status_code == 200

            # Pass
            resp = _post_event(client, session.slug, {"type": "pass_stick"}, 1)
            assert resp.status_code == 200
            assert resp.json()["turn_state"] == "passing"

    def test_stale_version_returns_409(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            _post_event(client, session.slug, {"type": "start_room"}, 0)
            resp = _post_event(client, session.slug, {"type": "pass_stick"}, 0)  # stale

        assert resp.status_code == 409
        assert resp.json()["code"] == "stale_version"

    def test_non_attendee_returns_403(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={keeper.slug},
            ),
            patch("totem.rooms.api.publish_state"),
        ):
            resp = _post_event(client, session.slug, {"type": "start_room"}, 0)

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_in_room"

    def test_room_not_found_returns_404(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value=set(),
            ),
            patch("totem.rooms.api.publish_state"),
        ):
            resp = _post_event(client, "nonexistent", {"type": "start_room"}, 0)

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_not_keeper_returns_403(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={keeper.slug, user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
        ):
            resp = _post_event(client, session.slug, {"type": "start_room"}, 0)

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"

    def test_end_room(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            _post_event(client, session.slug, {"type": "start_room"}, 0)
            resp = _post_event(
                client,
                session.slug,
                {"type": "end_room", "reason": "keeper_ended"},
                1,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ended"

    def test_end_room_sets_ended_at(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        assert session.ended_at is None

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            _post_event(client, session.slug, {"type": "start_room"}, 0)
            _post_event(
                client,
                session.slug,
                {"type": "end_room", "reason": "keeper_ended"},
                1,
            )

        session.refresh_from_db()
        assert session.ended_at is not None

    def test_start_room_mutes_all_except_speaker(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants") as mock_mute_all,
        ):
            resp = _post_event(client, session.slug, {"type": "start_room"}, 0)

        assert resp.status_code == 200
        mock_mute_all.assert_called_once_with(session.slug, except_identity=user.slug)


@pytest.mark.django_db
class TestGetState:
    def test_returns_state(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "waiting_room"
        assert data["session_slug"] == session.slug
        assert data["keeper"] == user.slug

    def test_non_attendee_returns_403(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        resp = _get_state(client, session.slug)

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_in_room"

    def test_room_not_found_returns_404(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        resp = _get_state(client, "nonexistent")

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_state_reflects_mutations(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            _post_event(client, session.slug, {"type": "start_room"}, 0)

        resp = _get_state(client, session.slug)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        assert resp.json()["version"] == 1


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------

BASE = "/api/mobile/protected/rooms"


def _make_joinable_session(keeper: User, attendees: list[User] | None = None):
    """Create a session that is currently joinable (start time in the near past)."""
    import datetime

    start = timezone.now() - datetime.timedelta(minutes=5)
    session = SessionFactory(space__author=keeper, start=start)
    session.attendees.add(keeper)
    if attendees:
        for u in attendees:
            session.attendees.add(u)
    return session


@pytest.mark.django_db
class TestJoinRoom:
    def test_join_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = _make_joinable_session(user)

        with patch("totem.rooms.api.create_access_token", return_value="fake-jwt-token"):
            resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 200
        assert resp.json()["token"] == "fake-jwt-token"
        assert user in session.joined.all()
        assert Room.objects.filter(session=session).exists()

    def test_join_not_joinable(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        # Session in the future — can_join returns False
        session = SessionFactory(space__author=user)
        session.attendees.add(user)

        resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_joinable"

    def test_join_session_not_found(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        resp = client.post(f"{BASE}/nonexistent/join")

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_join_tracks_analytics(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = _make_joinable_session(user)

        with (
            patch("totem.rooms.api.create_access_token", return_value="fake-jwt-token"),
            patch("totem.rooms.api.analytics") as mock_analytics,
        ):
            resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 200
        mock_analytics.event_joined.assert_called_once_with(user, session)

    def test_join_livekit_not_configured(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = _make_joinable_session(user)

        with patch(
            "totem.rooms.api.create_access_token",
            side_effect=LiveKitConfigurationError("not configured"),
        ):
            resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 500
        assert resp.json()["code"] == "livekit_error"


# ---------------------------------------------------------------------------
# Mute
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMuteParticipant:
    def test_mute_success(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with patch("totem.rooms.api.mute_participant") as mock_mute:
            resp = client.post(f"{BASE}/{session.slug}/mute/some-participant")

        assert resp.status_code == 200
        mock_mute.assert_called_once_with(session.slug, "some-participant")

    def test_mute_not_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        resp = client.post(f"{BASE}/{session.slug}/mute/some-participant")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"

    def test_mute_participant_not_found(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with patch(
            "totem.rooms.api.mute_participant",
            side_effect=ParticipantNotFoundError("not found"),
        ):
            resp = client.post(f"{BASE}/{session.slug}/mute/missing-user")

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_mute_room_not_found(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        resp = client.post(f"{BASE}/nonexistent/mute/some-participant")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Mute All
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMuteAll:
    def test_mute_all_success(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with patch("totem.rooms.api.mute_all_participants") as mock_mute_all:
            resp = client.post(f"{BASE}/{session.slug}/mute-all")

        assert resp.status_code == 200
        mock_mute_all.assert_called_once_with(session.slug, except_identity=keeper.slug)

    def test_mute_all_not_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        resp = client.post(f"{BASE}/{session.slug}/mute-all")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRemoveParticipant:
    def test_remove_success(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with patch("totem.rooms.api.remove_participant") as mock_remove:
            resp = client.post(f"{BASE}/{session.slug}/remove/some-participant")

        assert resp.status_code == 200
        mock_remove.assert_called_once_with(session.slug, "some-participant")

    def test_remove_not_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        resp = client.post(f"{BASE}/{session.slug}/remove/some-participant")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"

    def test_cannot_remove_self(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        resp = client.post(f"{BASE}/{session.slug}/remove/{keeper.slug}")

        assert resp.status_code == 400

    def test_remove_participant_not_found(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)  # pyright: ignore[reportAttributeAccessIssue]

        with patch(
            "totem.rooms.api.remove_participant",
            side_effect=ParticipantNotFoundError("not found"),
        ):
            resp = client.post(f"{BASE}/{session.slug}/remove/missing-user")

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"
