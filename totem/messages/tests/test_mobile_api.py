from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from django.test import Client
from django.urls import reverse

from totem.api.auth import generate_jwt_token
from totem.messages.models import Conversation, ConversationMembership, Message, SessionMessageRequest
from totem.messages.services import create_message, get_or_create_conversation
from totem.rooms.models import Room
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import KeeperProfileFactory, UserFactory


def authenticated_client(user: User) -> Client:
    return Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(user)}")


def keeper_with_profile(**kwargs) -> User:
    keeper = UserFactory(**kwargs)
    KeeperProfileFactory(user=keeper)
    return keeper


def relationship(
    keeper: User,
    participant: User,
    *,
    attendee: bool = True,
    joined: bool = False,
    **session_fields,
):
    if not keeper.is_keeper():
        KeeperProfileFactory(user=keeper)
    session = SessionFactory(space=SpaceFactory(author=keeper), **session_fields)
    if attendee:
        session.attendees.add(participant)
    if joined:
        session.joined.add(participant)
    return session


@pytest.mark.django_db
class TestConversationAPI:
    def test_open_conversation_returns_public_peer_only(self):
        keeper = UserFactory(name="Keeper", email="private@example.com")
        participant = UserFactory()
        relationship(keeper, participant)

        response = authenticated_client(participant).post(
            reverse("mobile-api:messages_conversation_open"),
            data={"recipient_slug": keeper.slug},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert set(data["peer"]) == {
            "slug",
            "name",
            "profile_image",
            "profile_avatar_seed",
            "profile_avatar_type",
        }
        assert data["peer"]["slug"] == keeper.slug
        assert "email" not in response.content.decode()

    @pytest.mark.parametrize("relationship_kind", ["unrelated", "wrong_keeper", "banned", "cancelled"])
    def test_open_denials_are_indistinguishable(self, relationship_kind: str):
        participant = UserFactory()
        recipient = UserFactory()
        if relationship_kind == "wrong_keeper":
            relationship(UserFactory(), participant)
        elif relationship_kind == "banned":
            session = relationship(recipient, participant)
            Room.objects.create(session=session, keeper=recipient.slug, banned_participants=[participant.slug])
        elif relationship_kind == "cancelled":
            session = relationship(recipient, participant)
            session.cancelled = True
            session.save(update_fields=["cancelled"])

        response = authenticated_client(participant).post(
            reverse("mobile-api:messages_conversation_open"),
            data={"recipient_slug": recipient.slug},
            content_type="application/json",
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}

    def test_space_author_without_keeper_profile_cannot_open_a_thread(self):
        keeper_without_profile = UserFactory()
        participant = UserFactory()
        session = SessionFactory(space=SpaceFactory(author=keeper_without_profile))
        session.attendees.add(participant)

        response = authenticated_client(participant).post(
            reverse("mobile-api:messages_conversation_open"),
            data={"recipient_slug": keeper_without_profile.slug},
            content_type="application/json",
        )

        assert response.status_code == 404

    def test_existing_conversation_is_hidden_after_relationship_ends(self):
        keeper = UserFactory()
        participant = UserFactory()
        session = relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        session.cancelled = True
        session.save(update_fields=["cancelled"])

        response = authenticated_client(participant).get(
            reverse("mobile-api:messages_history", kwargs={"conversation_id": conversation.pk})
        )

        assert response.status_code == 404

    def test_session_cookie_auth_uses_same_route(self, client: Client):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        client.force_login(participant)

        response = client.post(
            reverse("mobile-api:messages_conversation_open"),
            data={"recipient_slug": keeper.slug},
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_unauthenticated_request_is_rejected(self, client: Client):
        response = client.get(reverse("mobile-api:messages_conversations"))

        assert response.status_code == 401

    def test_inbox_is_newest_first_with_unread_counts_and_cursor(self):
        participant = UserFactory()
        old_keeper = UserFactory(name="Old")
        new_keeper = UserFactory(name="New")
        relationship(old_keeper, participant)
        relationship(new_keeper, participant)
        old_conversation = get_or_create_conversation(participant, old_keeper)
        new_conversation = get_or_create_conversation(participant, new_keeper)
        create_message(old_conversation, old_keeper, "Old message", None)
        create_message(new_conversation, new_keeper, "New message", None)

        first = authenticated_client(participant).get(
            reverse("mobile-api:messages_conversations"),
            {"limit": 1},
        )
        second = authenticated_client(participant).get(
            reverse("mobile-api:messages_conversations"),
            {"limit": 1, "cursor": first.json()["next_cursor"]},
        )

        assert first.status_code == second.status_code == 200
        assert first.json()["items"][0]["peer"]["name"] == "New"
        assert first.json()["items"][0]["unread_count"] == 1
        assert first.json()["total_unread_count"] == 2
        assert first.json()["items"][0]["last_message"]["text"] == "New message"
        assert second.json()["items"][0]["peer"]["name"] == "Old"
        assert second.json()["next_cursor"] is None
        assert set(first.json()["items"][0]["last_message"]) == {
            "id",
            "sender_slug",
            "text",
            "created_at",
            "is_mine",
        }

    def test_cold_conversation_lookup_returns_authorized_summary(self):
        keeper = UserFactory(name="Keeper")
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        create_message(conversation, keeper, "Latest", None)

        response = authenticated_client(participant).get(
            reverse("mobile-api:messages_conversation_detail", kwargs={"conversation_id": conversation.pk})
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(conversation.pk)
        assert response.json()["peer"]["slug"] == keeper.slug
        assert response.json()["last_message"]["text"] == "Latest"
        assert response.json()["unread_count"] == 1
        assert response.json()["updated_at"]

    def test_cold_conversation_lookup_is_non_disclosing(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        unrelated = UserFactory()
        client = authenticated_client(unrelated)

        inaccessible = client.get(
            reverse("mobile-api:messages_conversation_detail", kwargs={"conversation_id": conversation.pk})
        )
        absent = client.get(reverse("mobile-api:messages_conversation_detail", kwargs={"conversation_id": uuid4()}))

        assert inaccessible.status_code == absent.status_code == 404
        assert inaccessible.json() == absent.json() == {"detail": "Not Found"}

    def test_cold_conversation_lookup_reauthorizes_ban(self):
        keeper = UserFactory()
        participant = UserFactory()
        session = relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        Room.objects.create(session=session, keeper=keeper.slug, banned_participants=[participant.slug])

        response = authenticated_client(participant).get(
            reverse("mobile-api:messages_conversation_detail", kwargs={"conversation_id": conversation.pk})
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestRecipientDirectoryAPI:
    def test_participant_gets_only_messageable_keepers_in_recommendation_order(self):
        participant = UserFactory()
        without_conversation = UserFactory(name="No Existing", email="hidden-one@example.com")
        with_conversation = UserFactory(name="Existing", email="hidden-two@example.com")
        banned_keeper = UserFactory(name="Banned Keeper")
        unrelated = UserFactory(name="Unrelated")
        relationship(
            without_conversation,
            participant,
            title="Older Session",
            start=datetime.now(UTC) - timedelta(days=10),
        )
        relationship(
            with_conversation,
            participant,
            title="Fresh Session",
            start=datetime.now(UTC) - timedelta(days=1),
        )
        banned_session = relationship(banned_keeper, participant, title="Banned Session")
        Room.objects.create(
            session=banned_session,
            keeper=banned_keeper.slug,
            banned_participants=[participant.slug],
        )
        conversation = get_or_create_conversation(participant, with_conversation)

        response = authenticated_client(participant).get(reverse("mobile-api:messages_recipients"))

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "keepers"
        assert data["participants"] == []
        assert [entry["profile"]["slug"] for entry in data["keepers"]] == [
            without_conversation.slug,
            with_conversation.slug,
        ]
        assert data["keepers"][0]["existing_conversation_id"] is None
        assert data["keepers"][1]["existing_conversation_id"] == str(conversation.pk)
        assert all(entry["can_start_direct"] is True for entry in data["keepers"])
        assert banned_keeper.slug not in response.content.decode()
        assert unrelated.slug not in response.content.decode()
        assert "hidden-one@example.com" not in response.content.decode()
        assert "hidden-two@example.com" not in response.content.decode()

    @pytest.mark.parametrize(
        ("query", "expected_name"), [("fresh session", "Existing"), ("no existing", "No Existing")]
    )
    def test_participant_directory_filters_authorized_name_or_session_title(self, query: str, expected_name: str):
        participant = UserFactory()
        first_keeper = UserFactory(name="Existing")
        second_keeper = UserFactory(name="No Existing")
        relationship(first_keeper, participant, title="Fresh Session")
        relationship(second_keeper, participant, title="Other Session")

        response = authenticated_client(participant).get(
            reverse("mobile-api:messages_recipients"),
            {"query": query.upper()},
        )

        assert response.status_code == 200
        assert [entry["profile"]["name"] for entry in response.json()["keepers"]] == [expected_name]

    @pytest.mark.parametrize("params", [{"query": "x" * 101}, {"limit": 51}, {"limit": 0}])
    def test_recipient_directory_bounds_are_validated(self, params: dict[str, str | int]):
        response = authenticated_client(UserFactory()).get(reverse("mobile-api:messages_recipients"), params)

        assert response.status_code == 422

    def test_participant_directory_empty_results(self):
        participant = UserFactory()
        relationship(UserFactory(), participant, title="Known Session")

        response = authenticated_client(participant).get(
            reverse("mobile-api:messages_recipients"),
            {"query": "does not exist"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "kind": "keepers",
            "keepers": [],
            "participants": [],
            "next_cursor": None,
        }

    def test_participant_directory_uses_stable_cursor_paging(self):
        participant = UserFactory()
        for index in range(3):
            relationship(
                UserFactory(name=f"Keeper {index}"),
                participant,
                start=datetime.now(UTC) - timedelta(days=index),
            )
        client = authenticated_client(participant)
        first = client.get(reverse("mobile-api:messages_recipients"), {"limit": 2})
        second = client.get(
            reverse("mobile-api:messages_recipients"),
            {"limit": 2, "cursor": first.json()["next_cursor"]},
        )

        slugs = [entry["profile"]["slug"] for entry in first.json()["keepers"] + second.json()["keepers"]]
        assert first.status_code == second.status_code == 200
        assert len(slugs) == len(set(slugs)) == 3
        assert first.json()["next_cursor"]
        assert second.json()["next_cursor"] is None

    def test_dual_role_user_can_select_their_keepers_directory(self):
        dual_role_user = keeper_with_profile()
        other_keeper = keeper_with_profile(name="Other keeper")
        relationship(other_keeper, dual_role_user)
        relationship(dual_role_user, UserFactory())

        response = authenticated_client(dual_role_user).get(
            reverse("mobile-api:messages_recipients"),
            {"kind": "keepers"},
        )

        assert response.status_code == 200
        assert response.json()["kind"] == "keepers"
        assert [entry["profile"]["slug"] for entry in response.json()["keepers"]] == [other_keeper.slug]

    def test_keeper_gets_participants_with_latest_qualifying_session_metadata(self):
        keeper = keeper_with_profile()
        participant = UserFactory(name="Participant", email="participant-secret@example.com")
        banned = UserFactory(name="Banned")
        unrelated = UserFactory(name="Unrelated")
        space = SpaceFactory(author=keeper, title="Fallback Space Title")
        older = SessionFactory(
            space=space,
            title="Older Session",
            start=datetime.now(UTC) - timedelta(days=5),
        )
        latest = SessionFactory(
            space=space,
            title="",
            start=datetime.now(UTC) - timedelta(days=1),
        )
        older.attendees.add(participant)
        latest.joined.add(participant)
        banned_session = SessionFactory(space=space, title="Private Session")
        banned_session.attendees.add(banned)
        Room.objects.create(session=banned_session, keeper=keeper.slug, banned_participants=[banned.slug])
        conversation = get_or_create_conversation(keeper, participant)

        response = authenticated_client(keeper).get(reverse("mobile-api:messages_recipients"))

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "participants"
        assert data["keepers"] == []
        assert len(data["participants"]) == 1
        entry = data["participants"][0]
        assert entry["profile"]["slug"] == participant.slug
        assert entry["existing_conversation_id"] == str(conversation.pk)
        assert entry["can_start_direct"] is True
        assert entry["session_slug"] == latest.slug
        assert entry["session_title"] == "Fallback Space Title"
        returned_start = datetime.fromisoformat(entry["session_start"].replace("Z", "+00:00"))
        assert abs(returned_start - latest.start) < timedelta(milliseconds=1)
        assert banned.slug not in response.content.decode()
        assert unrelated.slug not in response.content.decode()
        assert "participant-secret@example.com" not in response.content.decode()

    @pytest.mark.parametrize("query", ["PARTICIPANT", "fallback space title"])
    def test_keeper_directory_filters_name_or_session_title(self, query: str):
        keeper = keeper_with_profile()
        participant = UserFactory(name="Participant")
        session = SessionFactory(space=SpaceFactory(author=keeper, title="Fallback Space Title"))
        session.attendees.add(participant)

        response = authenticated_client(keeper).get(
            reverse("mobile-api:messages_recipients"),
            {"query": query},
        )

        assert response.status_code == 200
        assert [entry["profile"]["slug"] for entry in response.json()["participants"]] == [participant.slug]

    def test_keeper_directory_no_participants(self):
        keeper = keeper_with_profile()
        SpaceFactory(author=keeper)

        response = authenticated_client(keeper).get(reverse("mobile-api:messages_recipients"))

        assert response.status_code == 200
        assert response.json() == {
            "kind": "participants",
            "keepers": [],
            "participants": [],
            "next_cursor": None,
        }


@pytest.mark.django_db
class TestMessageAPI:
    def test_send_trims_and_deduplicates_then_notifies_only_peer(self, django_capture_on_commit_callbacks):
        keeper = UserFactory(name="Keeper")
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        url = reverse("mobile-api:messages_send", kwargs={"conversation_id": conversation.pk})
        client = authenticated_client(participant)

        client_message_id = str(uuid4())
        with (
            patch("totem.messages.services.send_notification_to_user", return_value=True) as send,
            django_capture_on_commit_callbacks(execute=True),
        ):
            first = client.post(
                url,
                data={"text": "  Hello  ", "client_message_id": client_message_id},
                content_type="application/json",
            )
            duplicate = client.post(
                url,
                data={"text": "Different", "client_message_id": client_message_id},
                content_type="application/json",
            )

        assert first.status_code == duplicate.status_code == 201
        assert first.json() == duplicate.json()
        assert first.json()["text"] == "Hello"
        assert first.json()["client_message_id"] == client_message_id
        assert Message.objects.count() == 1
        send.assert_called_once()
        assert send.call_args.args[0] == keeper
        assert send.call_args.kwargs["title"] == "New private message"
        assert send.call_args.kwargs["body"] == "Open Totem to read it."
        assert send.call_args.kwargs["data"] == {
            "type": "message_received",
            "conversation_id": str(conversation.pk),
            "message_id": first.json()["id"],
            "path": f"/messages/conversations/{conversation.pk}",
        }
        assert all(isinstance(value, str) for value in send.call_args.kwargs["data"].values())
        assert "Hello" not in send.call_args.kwargs["data"].values()

    def test_notification_exception_is_non_fatal_after_commit(self, django_capture_on_commit_callbacks):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)

        with (
            patch("totem.messages.services.send_notification_to_user", side_effect=RuntimeError("FCM down")),
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = authenticated_client(participant).post(
                reverse("mobile-api:messages_send", kwargs={"conversation_id": conversation.pk}),
                data={"text": "Committed", "client_message_id": None},
                content_type="application/json",
            )

        assert response.status_code == 201
        assert Message.objects.get().body == "Committed"

    @pytest.mark.parametrize("text", ["", "   ", "x" * 4001])
    def test_invalid_text_is_rejected(self, text: str):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)

        response = authenticated_client(participant).post(
            reverse("mobile-api:messages_send", kwargs={"conversation_id": conversation.pk}),
            data={"text": text, "client_message_id": None},
            content_type="application/json",
        )

        assert response.status_code == 422
        assert Message.objects.count() == 0

    def test_blank_client_message_id_is_rejected(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)

        response = authenticated_client(participant).post(
            reverse("mobile-api:messages_send", kwargs={"conversation_id": conversation.pk}),
            data={"text": "Hello", "client_message_id": "   "},
            content_type="application/json",
        )

        assert response.status_code == 422
        assert Message.objects.count() == 0

    def test_history_can_poll_newer_messages_with_an_after_cursor(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        first = create_message(conversation, keeper, "First", None)
        baseline = authenticated_client(participant).get(
            reverse("mobile-api:messages_history", kwargs={"conversation_id": conversation.pk}),
            {"limit": 10},
        )
        create_message(conversation, keeper, "Second", None)
        create_message(conversation, keeper, "Third", None)

        response = authenticated_client(participant).get(
            reverse("mobile-api:messages_history", kwargs={"conversation_id": conversation.pk}),
            {"after": baseline.json()["next_after"], "limit": 10},
        )

        assert baseline.status_code == response.status_code == 200
        assert baseline.json()["items"][0]["id"] == str(first.pk)
        assert [item["text"] for item in response.json()["items"]] == ["Second", "Third"]
        assert response.json()["next_after"] == response.json()["items"][-1]["cursor"]

    def test_history_rejects_before_and_after_together(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        create_message(conversation, keeper, "First", None)
        cursor = (
            authenticated_client(participant)
            .get(reverse("mobile-api:messages_history", kwargs={"conversation_id": conversation.pk}))
            .json()["next_after"]
        )

        response = authenticated_client(participant).get(
            reverse("mobile-api:messages_history", kwargs={"conversation_id": conversation.pk}),
            {"before": cursor, "after": cursor},
        )

        assert response.status_code == 422

    def test_history_uses_stable_keyset_paging_for_equal_timestamps(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        messages = [create_message(conversation, participant, f"Message {index}", None) for index in range(4)]
        tied_at = datetime(2026, 1, 1, tzinfo=UTC)
        Message.objects.filter(pk__in=[message.pk for message in messages]).update(created_at=tied_at)
        url = reverse("mobile-api:messages_history", kwargs={"conversation_id": conversation.pk})
        client = authenticated_client(participant)

        first = client.get(url, {"limit": 2})
        second = client.get(url, {"limit": 2, "before": first.json()["next_before"]})

        assert first.status_code == second.status_code == 200
        ids = [item["id"] for item in first.json()["items"] + second.json()["items"]]
        assert len(ids) == len(set(ids)) == 4
        assert first.json()["has_more"] is True
        assert second.json()["has_more"] is False
        assert second.json()["next_before"] is None
        assert all(item["created_at"] for item in first.json()["items"] + second.json()["items"])
        assert "Today" not in first.content.decode() + second.content.decode()

    def test_read_rejects_message_from_another_conversation(self):
        participant = UserFactory()
        keeper = UserFactory()
        other_keeper = UserFactory()
        relationship(keeper, participant)
        relationship(other_keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        other = get_or_create_conversation(participant, other_keeper)
        message = create_message(other, other_keeper, "Other", None)

        response = authenticated_client(participant).post(
            reverse("mobile-api:messages_read", kwargs={"conversation_id": conversation.pk}),
            data={"last_read_message_id": str(message.pk)},
            content_type="application/json",
        )

        assert response.status_code == 422

    def test_sync_returns_changed_summaries_not_history(self):
        keeper = UserFactory()
        participant = UserFactory()
        relationship(keeper, participant)
        conversation = get_or_create_conversation(participant, keeper)
        create_message(conversation, keeper, "One", None)
        create_message(conversation, keeper, "Two", None)

        response = authenticated_client(participant).get(reverse("mobile-api:messages_sync"), {"limit": 10})

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert "messages" not in data["items"][0]
        assert data["items"][0]["last_message"]["text"] == "Two"
        assert data["next_cursor"]
        assert data["total_unread_count"] == 2


@pytest.mark.django_db
class TestSessionParticipantsAPI:
    def test_keeper_gets_only_eligible_non_banned_public_profiles(self):
        keeper = keeper_with_profile()
        attendee = UserFactory(name="Attendee", email="attendee-secret@example.com")
        joined = UserFactory(name="Joined")
        banned = UserFactory(name="Banned")
        unrelated = UserFactory(name="Unrelated")
        session = SessionFactory(space=SpaceFactory(author=keeper))
        session.attendees.add(attendee, banned)
        session.joined.add(joined)
        Room.objects.create(session=session, keeper=keeper.slug, banned_participants=[banned.slug])

        response = authenticated_client(keeper).get(
            reverse("mobile-api:messages_session_participants", kwargs={"session_slug": session.slug})
        )

        assert response.status_code == 200
        data = response.json()
        assert {profile["profile"]["slug"] for profile in data["items"]} == {attendee.slug, joined.slug}
        assert unrelated.slug not in response.content.decode()
        assert "attendee-secret@example.com" not in response.content.decode()
        assert all(
            set(profile["profile"]) == {"slug", "name", "profile_image", "profile_avatar_seed", "profile_avatar_type"}
            for profile in data["items"]
        )
        assert all(profile["reviews_count"] is None for profile in data["items"])
        assert data["next_cursor"] is None

    def test_session_participants_are_paginated(self):
        keeper = keeper_with_profile()
        session = SessionFactory(space=SpaceFactory(author=keeper))
        attendees = [UserFactory(name=f"Attendee {index}") for index in range(3)]
        session.attendees.add(*attendees)
        client = authenticated_client(keeper)

        first = client.get(
            reverse("mobile-api:messages_session_participants", kwargs={"session_slug": session.slug}),
            {"limit": 2},
        )
        second = client.get(
            reverse("mobile-api:messages_session_participants", kwargs={"session_slug": session.slug}),
            {"limit": 2, "cursor": first.json()["next_cursor"]},
        )

        slugs = [item["profile"]["slug"] for item in first.json()["items"] + second.json()["items"]]
        assert len(slugs) == len(set(slugs)) == 3

    def test_non_owner_gets_404(self):
        session = SessionFactory()

        response = authenticated_client(UserFactory()).get(
            reverse("mobile-api:messages_session_participants", kwargs={"session_slug": session.slug})
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestSessionMessageAPI:
    def test_keeper_fans_out_to_independent_conversations_idempotently(self, django_capture_on_commit_callbacks):
        keeper = keeper_with_profile()
        first = UserFactory()
        second = UserFactory()
        session = SessionFactory(space=SpaceFactory(author=keeper))
        session.attendees.add(first, second)
        payload = {
            "recipient_slugs": [first.slug, second.slug],
            "text": "  Session reminder  ",
            "client_request_id": str(uuid4()),
        }
        url = reverse("mobile-api:messages_session_send", kwargs={"session_slug": session.slug})

        with (
            patch("totem.messages.services.send_notification_to_user", return_value=True) as send,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = authenticated_client(keeper).post(url, data=payload, content_type="application/json")
            retry = authenticated_client(keeper).post(url, data=payload, content_type="application/json")

        assert response.status_code == retry.status_code == 201
        assert response.json() == retry.json()
        assert response.json()["requested_count"] == response.json()["sent_count"] == 2
        assert len(response.json()["recipients"]) == 2
        assert Conversation.objects.count() == 2
        assert Message.objects.count() == 2
        assert SessionMessageRequest.objects.count() == 1
        assert {message.body for message in Message.objects.all()} == {"Session reminder"}
        assert {message.conversation_id for message in Message.objects.all()} == {
            UUID(result["conversation_id"]) for result in response.json()["recipients"]
        }
        assert send.call_count == 2
        assert {
            ConversationMembership.objects.get(
                conversation=message.conversation, user=message.conversation.peer_for(keeper.pk)
            ).unread_count
            for message in Message.objects.all()
        } == {1}

    def test_session_send_rejects_non_members_without_partial_persistence(self):
        keeper = keeper_with_profile()
        attendee = UserFactory()
        outsider = UserFactory()
        session = SessionFactory(space=SpaceFactory(author=keeper))
        session.attendees.add(attendee)

        response = authenticated_client(keeper).post(
            reverse("mobile-api:messages_session_send", kwargs={"session_slug": session.slug}),
            data={
                "recipient_slugs": [attendee.slug, outsider.slug],
                "text": "Hello",
                "client_request_id": str(uuid4()),
            },
            content_type="application/json",
        )

        assert response.status_code == 422
        assert Conversation.objects.count() == Message.objects.count() == SessionMessageRequest.objects.count() == 0

    def test_session_send_hides_non_owner_and_banned_participants(self):
        keeper = keeper_with_profile()
        attendee = UserFactory()
        session = SessionFactory(space=SpaceFactory(author=keeper))
        session.attendees.add(attendee)
        Room.objects.create(session=session, keeper=keeper.slug, banned_participants=[attendee.slug])
        payload = {"recipient_slugs": [attendee.slug], "text": "Hello", "client_request_id": str(uuid4())}

        banned = authenticated_client(keeper).post(
            reverse("mobile-api:messages_session_send", kwargs={"session_slug": session.slug}),
            data=payload,
            content_type="application/json",
        )
        non_owner = authenticated_client(UserFactory()).post(
            reverse("mobile-api:messages_session_send", kwargs={"session_slug": session.slug}),
            data=payload,
            content_type="application/json",
        )

        assert banned.status_code == 422
        assert non_owner.status_code == 404
        assert Message.objects.count() == 0
