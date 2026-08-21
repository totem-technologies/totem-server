import datetime
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from totem.rooms.livekit import LiveKitConfigurationError
from totem.rooms.models import Room
from totem.rooms.schemas import EndReason, RemoveReason, RoomStatus, TurnState
from totem.spaces.models import Space
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
        Room.objects.get_or_create_for_session(session)

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

    def test_start_room_with_prompt(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            resp = _post_event(
                client,
                session.slug,
                {"type": "start_room", "prompt": "Welcome everyone"},
                0,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["round_number"] == 1
        assert data["round_message"] == "Welcome everyone"

    def test_start_room_prompt_exceeds_max_length(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.api.get_connected_participants", return_value={user.slug}),
            patch("totem.rooms.api.publish_state"),
        ):
            resp = _post_event(
                client,
                session.slug,
                {"type": "start_room", "prompt": "x" * 2001},
                0,
            )

        assert resp.status_code == 422

    def test_full_pass_accept_cycle(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        user1 = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user1)
        Room.objects.get_or_create_for_session(session)

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
        Room.objects.get_or_create_for_session(session)

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
        Room.objects.get_or_create_for_session(session)

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
        Room.objects.get_or_create_for_session(session)

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
        Room.objects.get_or_create_for_session(session)

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
        Room.objects.get_or_create_for_session(session)

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
        Room.objects.get_or_create_for_session(session)

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

    def test_keeper_pass_can_include_optional_prompt(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        user1 = UserFactory()
        user2 = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user1, user2)
        Room.objects.get_or_create_for_session(session)

        connected = {keeper.slug, user1.slug, user2.slug}

        with (
            patch("totem.rooms.api.get_connected_participants", return_value=connected),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            start = _post_event(client, session.slug, {"type": "start_room"}, 0)
            assert start.status_code == 200

            resp = _post_event(
                client,
                session.slug,
                {"type": "pass_stick", "prompt": "What are you carrying today?"},
                1,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["round_number"] == 1
        assert data["round_message"] == "What are you carrying today?"

    def test_set_prompt(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        user1 = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user1)
        Room.objects.get_or_create_for_session(session)

        connected = {keeper.slug, user1.slug}

        with (
            patch("totem.rooms.api.get_connected_participants", return_value=connected),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            start = _post_event(client, session.slug, {"type": "start_room"}, 0)
            assert start.status_code == 200

            resp = _post_event(
                client,
                session.slug,
                {"type": "set_prompt", "prompt": "Updated mid-round"},
                1,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["round_message"] == "Updated mid-round"
        assert data["round_number"] == 1  # round doesn't change

    def test_set_prompt_non_keeper_rejected(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        user1 = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user1)
        Room.objects.get_or_create_for_session(session)

        connected = {keeper.slug, user1.slug}

        with (
            patch("totem.rooms.api.get_connected_participants", return_value=connected),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            _post_event(client, session.slug, {"type": "start_room"}, 0)

        user1_client = Client()
        user1_client.force_login(user1)

        with (
            patch("totem.rooms.api.get_connected_participants", return_value=connected),
            patch("totem.rooms.api.publish_state"),
        ):
            resp = _post_event(
                user1_client,
                session.slug,
                {"type": "set_prompt", "prompt": "Hijacked"},
                1,
            )

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"

    def test_set_prompt_exceeds_max_length(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        user1 = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user1)
        Room.objects.get_or_create_for_session(session)

        connected = {keeper.slug, user1.slug}

        with (
            patch("totem.rooms.api.get_connected_participants", return_value=connected),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            _post_event(client, session.slug, {"type": "start_room"}, 0)

            resp = _post_event(
                client,
                session.slug,
                {"type": "set_prompt", "prompt": "x" * 2001},
                1,
            )

        assert resp.status_code == 422


@pytest.mark.django_db
class TestGetState:
    def test_returns_state(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.api.get_connected_participants", return_value={user.slug}) as mock_connected,
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "waiting_room"
        assert data["session_slug"] == session.slug
        assert data["keeper"] == user.slug
        mock_connected.assert_called_once_with(session.slug)
        mock_publish.assert_called_once()
        assert mock_publish.call_args.args == (session.slug, session.room.to_state())

    def test_attendee_state_request_does_not_reconcile(self, client_with_user: tuple[Client, User]):
        client, attendee = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(attendee)
        Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.api.get_connected_participants") as mock_connected,
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        mock_connected.assert_not_called()
        mock_publish.assert_not_called()

    def test_non_attendee_returns_403(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.api.get_connected_participants") as mock_connected,
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_in_room"
        mock_connected.assert_not_called()
        mock_publish.assert_not_called()

    def test_room_not_found_returns_404(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        with (
            patch("totem.rooms.api.get_connected_participants") as mock_connected,
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, "nonexistent")

        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"
        mock_connected.assert_not_called()
        mock_publish.assert_not_called()

    def test_state_reflects_mutations(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)
        session.attendees.add(user)
        Room.objects.get_or_create_for_session(session)

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={user.slug},
            ),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.mute_all_participants"),
        ):
            _post_event(client, session.slug, {"type": "start_room"}, 0)

        with (
            patch("totem.rooms.api.get_connected_participants", return_value={user.slug}),
            patch("totem.rooms.api.publish_state"),
        ):
            resp = _get_state(client, session.slug)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        assert resp.json()["version"] == 1

    def test_keeper_state_request_reconciles_and_persists_participants(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        participant = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, participant)
        room = Room.objects.get_or_create_for_session(session)

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={keeper.slug, participant.slug},
            ),
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        assert resp.json()["talking_order"] == [keeper.slug, participant.slug]
        room.refresh_from_db()
        assert room.talking_order == [keeper.slug, participant.slug]
        assert room.state_version == 0
        mock_publish.assert_called_once()
        published_slug, published_state = mock_publish.call_args.args
        assert published_slug == session.slug
        assert published_state.talking_order == [keeper.slug, participant.slug]

    def test_keeper_state_request_repairs_disconnected_speaker(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        participant = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, participant)
        room = Room.objects.get_or_create_for_session(session)
        room.talking_order = [keeper.slug, participant.slug]
        room.status = RoomStatus.ACTIVE
        room.turn_state = TurnState.PASSING
        room.current_speaker = participant.slug
        room.next_speaker = keeper.slug
        room.save()

        with (
            patch("totem.rooms.api.get_connected_participants", return_value={keeper.slug}),
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        assert resp.json()["current_speaker"] == keeper.slug
        assert resp.json()["next_speaker"] == keeper.slug
        assert resp.json()["turn_state"] == "speaking"
        room.refresh_from_db()
        assert room.current_speaker == keeper.slug
        assert room.next_speaker == keeper.slug
        assert room.turn_state == TurnState.SPEAKING
        assert room.state_version == 0
        published_state = mock_publish.call_args.args[1]
        assert published_state.current_speaker == keeper.slug
        assert published_state.next_speaker == keeper.slug
        assert published_state.turn_state == TurnState.SPEAKING

    def test_livekit_failure_does_not_mutate_room(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        room = Room.objects.get_or_create_for_session(session)
        original_order = room.talking_order

        with (
            patch("totem.rooms.api.get_connected_participants", return_value=None),
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        room.refresh_from_db()
        assert room.talking_order == original_order
        mock_publish.assert_not_called()

    def test_empty_livekit_room_does_not_clear_active_speakers(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        participant = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, participant)
        room = Room.objects.get_or_create_for_session(session)
        room.talking_order = [keeper.slug, participant.slug]
        room.status = RoomStatus.ACTIVE
        room.turn_state = TurnState.PASSING
        room.current_speaker = participant.slug
        room.next_speaker = keeper.slug
        room.save()

        with (
            patch("totem.rooms.api.get_connected_participants", return_value=set()),
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        assert resp.json()["current_speaker"] == participant.slug
        assert resp.json()["next_speaker"] == keeper.slug
        assert resp.json()["turn_state"] == "passing"
        room.refresh_from_db()
        assert room.current_speaker == participant.slug
        assert room.next_speaker == keeper.slug
        assert room.turn_state == TurnState.PASSING
        mock_publish.assert_not_called()

    def test_keeper_reconciliation_excludes_banned_participants(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        banned = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, banned)
        room = Room.objects.get_or_create_for_session(session)
        room.talking_order = [keeper.slug]
        room.banned_participants = [banned.slug]
        room.save(update_fields=["talking_order", "banned_participants"])

        with (
            patch(
                "totem.rooms.api.get_connected_participants",
                return_value={keeper.slug, banned.slug},
            ),
            patch("totem.rooms.api.publish_state") as mock_publish,
        ):
            resp = _get_state(client, session.slug)

        assert resp.status_code == 200
        assert banned.slug not in resp.json()["talking_order"]
        room.refresh_from_db()
        assert banned.slug not in room.talking_order
        published_state = mock_publish.call_args.args[1]
        assert banned.slug not in published_state.talking_order


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------

BASE = "/api/mobile/protected/rooms"


def _make_joinable_session(keeper: User, attendees: list[User] | None = None):
    """Create a session that is currently joinable (start time in the near past)."""
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

        with (
            patch("totem.rooms.api.create_access_token", return_value="fake-jwt-token"),
            patch("totem.rooms.api.get_connected_participants", return_value={}),
        ):
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
            patch("totem.rooms.api.get_connected_participants", return_value={}),
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

    def test_join_banned_returns_403(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = _make_joinable_session(keeper, attendees=[user])
        room = Room.objects.get_or_create_for_session(session)
        room.banned_participants = [user.slug]
        room.save()

        resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 403
        assert resp.json()["code"] == "banned"

    def test_join_already_connected(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = _make_joinable_session(user)
        session.space.meeting_provider = Space.MeetingProviderChoices.LIVEKIT
        session.space.save()
        session.joined.add(user)

        with (
            patch("totem.rooms.api.create_access_token", return_value="fake-jwt-token"),
            patch("totem.rooms.api.get_connected_participants", return_value={user.slug}),
        ):
            resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 200
        assert resp.json()["token"] == "fake-jwt-token"
        assert resp.json()["is_already_present"] is True

    def test_join_rejoin_livekit_after_timeout(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        start = timezone.now() - datetime.timedelta(minutes=65)
        session = SessionFactory(
            space__author=user,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=start,
            duration_minutes=60,
        )
        session.attendees.add(user)
        session.joined.add(user)

        with (
            patch("totem.rooms.api.create_access_token", return_value="fake-jwt-token"),
            patch("totem.rooms.api.get_connected_participants", return_value={}),
        ):
            resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 200
        assert resp.json()["token"] == "fake-jwt-token"

    def test_join_rejoin_livekit_denied_when_ended(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        start = timezone.now() - datetime.timedelta(minutes=65)
        session = SessionFactory(
            space__author=user,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=start,
            duration_minutes=60,
        )
        session.attendees.add(user)
        session.joined.add(user)
        session.ended_at = timezone.now()
        session.save()

        resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_joinable"

    def test_join_rejoin_google_meet_after_timeout(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        start = timezone.now() - datetime.timedelta(minutes=65)
        session = SessionFactory(
            space__author=user,
            start=start,
            duration_minutes=60,
        )
        session.attendees.add(user)
        session.joined.add(user)

        resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_joinable"

    def test_join_livekit_first_time_after_timeout(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        start = timezone.now() - datetime.timedelta(minutes=65)
        session = SessionFactory(
            space__author=user,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=start,
            duration_minutes=60,
        )
        session.attendees.add(user)

        resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_joinable"

    def test_join_ended_room_rejected(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        start = timezone.now() - datetime.timedelta(minutes=5)
        session = SessionFactory(
            space__author=user,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=start,
            duration_minutes=60,
        )
        session.attendees.add(user)
        session.joined.add(user)

        room = Room.objects.get_or_create_for_session(session)
        room.status = RoomStatus.ENDED
        room.end_reason = EndReason.KEEPER_ABSENT
        room.save()

        resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 403
        assert resp.json()["code"] == "room_already_ended"

    def test_join_empty_room_past_duration_rejected(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        start = timezone.now() - datetime.timedelta(minutes=65)
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=start,
            duration_minutes=60,
        )
        session.attendees.add(keeper, user)
        session.joined.add(user)

        with patch("totem.rooms.api.get_connected_participants", return_value=set()):
            resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_joinable"

    def test_join_populated_room_past_duration_allowed(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        start = timezone.now() - datetime.timedelta(minutes=65)
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=start,
            duration_minutes=60,
        )
        session.attendees.add(keeper, user)
        session.joined.add(user)

        with (
            patch("totem.rooms.api.create_access_token", return_value="fake-jwt-token"),
            patch("totem.rooms.api.get_connected_participants", return_value={keeper.slug}),
        ):
            resp = client.post(f"{BASE}/{session.slug}/join")

        assert resp.status_code == 200
        assert resp.json()["token"] == "fake-jwt-token"


# ---------------------------------------------------------------------------
# Mute
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMuteParticipant:
    def test_mute_success(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)

        with patch("totem.rooms.api.mute_participant") as mock_mute:
            resp = client.post(f"{BASE}/{session.slug}/mute/some-participant")

        assert resp.status_code == 200
        mock_mute.assert_called_once_with(session.slug, "some-participant")

    def test_mute_not_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)

        resp = client.post(f"{BASE}/{session.slug}/mute/some-participant")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"

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
        Room.objects.get_or_create_for_session(session)

        with patch("totem.rooms.api.mute_all_participants") as mock_mute_all:
            resp = client.post(f"{BASE}/{session.slug}/mute-all")

        assert resp.status_code == 200
        mock_mute_all.assert_called_once_with(session.slug, except_identity=keeper.slug)

    def test_mute_all_not_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)

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
        Room.objects.get_or_create_for_session(session)

        with patch("totem.rooms.api.remove_participant") as mock_remove:
            resp = client.post(f"{BASE}/{session.slug}/remove/some-participant")

        assert resp.status_code == 200
        mock_remove.assert_called_once_with(session.slug, "some-participant", reason=RemoveReason.REMOVE)

    def test_remove_not_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)

        resp = client.post(f"{BASE}/{session.slug}/remove/some-participant")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"

    def test_cannot_remove_self(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)

        resp = client.post(f"{BASE}/{session.slug}/remove/{keeper.slug}")

        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_transition"


# ---------------------------------------------------------------------------
# Disable Camera
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDisableCamera:
    def test_disable_camera_success(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper)
        Room.objects.get_or_create_for_session(session)

        with patch("totem.rooms.api.disable_camera_participant") as mock_disable:
            resp = client.post(f"{BASE}/{session.slug}/disable-camera/some-participant")

        assert resp.status_code == 200
        mock_disable.assert_called_once_with(session.slug, "some-participant")

    def test_disable_camera_not_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)

        resp = client.post(f"{BASE}/{session.slug}/disable-camera/some-participant")

        assert resp.status_code == 403
        assert resp.json()["code"] == "not_keeper"

    def test_disable_camera_room_not_found(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        resp = client.post(f"{BASE}/nonexistent/disable-camera/some-participant")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Ban / Unban
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBanParticipant:
    def test_ban_success(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        participant = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, participant)
        Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.api.get_connected_participants", return_value={keeper.slug, participant.slug}),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.remove_participant"),
        ):
            resp = _post_event(
                client, session.slug, {"type": "ban_participant", "participant_slug": participant.slug}, 0
            )

        assert resp.status_code == 200
        assert participant.slug in resp.json()["banned_participants"]

    def test_ban_calls_remove_participant(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        participant = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, participant)
        Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.api.get_connected_participants", return_value={keeper.slug, participant.slug}),
            patch("totem.rooms.api.publish_state"),
            patch("totem.rooms.api.remove_participant") as mock_remove,
        ):
            _post_event(client, session.slug, {"type": "ban_participant", "participant_slug": participant.slug}, 0)

        mock_remove.assert_called_once_with(session.slug, participant.slug, reason=RemoveReason.BAN)


@pytest.mark.django_db
class TestUnbanParticipant:
    def test_unban_success(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        participant = UserFactory()
        session = SessionFactory(space__author=keeper)
        session.attendees.add(keeper, participant)
        room = Room.objects.get_or_create_for_session(session)
        room.banned_participants = [participant.slug]
        room.save()

        with (
            patch("totem.rooms.api.get_connected_participants", return_value={keeper.slug}),
            patch("totem.rooms.api.publish_state"),
        ):
            resp = _post_event(
                client, session.slug, {"type": "unban_participant", "participant_slug": participant.slug}, 0
            )

        assert resp.status_code == 200
        assert participant.slug not in resp.json()["banned_participants"]

    def test_unbanned_user_can_rejoin(self, client_with_user: tuple[Client, User]):
        client, keeper = client_with_user
        participant = UserFactory()
        session = _make_joinable_session(keeper, attendees=[participant])
        room = Room.objects.get_or_create_for_session(session)
        room.banned_participants = [participant.slug]
        room.save()

        # Banned user cannot join
        participant_client = Client()
        participant_client.force_login(participant)
        resp = participant_client.post(f"{BASE}/{session.slug}/join")
        assert resp.status_code == 403
        assert resp.json()["code"] == "banned"

        # Keeper unbans the participant
        with (
            patch("totem.rooms.api.get_connected_participants", return_value={keeper.slug}),
            patch("totem.rooms.api.publish_state"),
        ):
            unban_resp = _post_event(
                client, session.slug, {"type": "unban_participant", "participant_slug": participant.slug}, 0
            )
        assert unban_resp.status_code == 200

        # Unbanned user can now join
        with (
            patch("totem.rooms.api.create_access_token", return_value="fake-jwt-token"),
            patch("totem.rooms.api.get_connected_participants", return_value={keeper.slug}),
        ):
            join_resp = participant_client.post(f"{BASE}/{session.slug}/join")

        assert join_resp.status_code == 200
        assert join_resp.json()["token"] == "fake-jwt-token"
