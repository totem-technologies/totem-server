import csv
import datetime
import io
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import transaction
from django.test import Client, RequestFactory
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import escape

from totem.reporting.metrics import session_metrics
from totem.reporting.periods import ReportPeriod
from totem.rooms.models import Room, RoomEventLog
from totem.rooms.schemas import ErrorCode, RoomStatus, StartRoomEvent, TransitionError
from totem.rooms.state_machine import apply_event
from totem.spaces.admin import SessionPromptInlineForm, SpaceAdmin
from totem.spaces.models import Session, SessionFeedback, SessionPrompt, SessionRound, SessionRoundState
from totem.users.models import User
from totem.users.tests.factories import UserFactory

from .factories import SessionFactory, SpaceFactory


class TestSpaceAdmin:
    @pytest.mark.django_db(transaction=True)
    def test_changing_author_syncs_existing_active_room_and_broadcasts_on_commit(self) -> None:
        old_author = UserFactory()
        new_author = UserFactory()
        space = SpaceFactory(author=old_author)
        session = SessionFactory(space=space)
        room = Room.objects.get_or_create_for_session(session)
        room.status = RoomStatus.ACTIVE
        room.save(update_fields=["status"])
        request = RequestFactory().post("/")
        request.user = new_author
        space.author = new_author
        model_admin = SpaceAdmin(type(space), AdminSite())

        with patch("totem.rooms.state_machine.publish_state") as publish_state:
            with transaction.atomic():
                model_admin.save_model(request, space, None, True)
                room.refresh_from_db()
                assert room.keeper == new_author.slug
                assert session.attendees.filter(pk=new_author.pk).exists()
                assert room.state_version == 1
                publish_state.assert_not_called()

        assert room.keeper == new_author.slug
        assert room.state_version == 1
        event = RoomEventLog.objects.get(room=room)
        assert event.version == 1
        assert event.snapshot["keeper"] == new_author.slug
        publish_state.assert_called_once()
        assert publish_state.call_args.args[0] == session.slug
        assert publish_state.call_args.args[1].keeper == new_author.slug

    def test_keeper_change_updates_who_can_perform_keeper_actions(self, db) -> None:
        old_author = UserFactory()
        new_author = UserFactory()
        participant = UserFactory()
        space = SpaceFactory(author=old_author)
        session = SessionFactory(space=space)
        session.attendees.add(old_author, new_author, participant)
        room = Room.objects.get_or_create_for_session(session)
        room.talking_order = [old_author.slug, new_author.slug, participant.slug]
        room.save(update_fields=["talking_order"])
        request = RequestFactory().post("/")
        request.user = new_author
        space.author = new_author

        SpaceAdmin(type(space), AdminSite()).save_model(request, space, None, True)

        connected = {old_author.slug, new_author.slug, participant.slug}
        with pytest.raises(TransitionError) as exc_info:
            apply_event(session.slug, old_author.slug, StartRoomEvent(), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

        state = apply_event(session.slug, new_author.slug, StartRoomEvent(), 1, connected)

        assert state.keeper == new_author.slug
        assert state.status == RoomStatus.ACTIVE
        assert state.version == 2

    def test_changing_author_does_not_create_rooms_or_update_ended_rooms(self, db) -> None:
        old_author = UserFactory()
        new_author = UserFactory()
        space = SpaceFactory(author=old_author)
        no_room_session = SessionFactory(space=space)
        ended_session = SessionFactory(space=space)
        ended_room = Room.objects.get_or_create_for_session(ended_session)
        ended_room.status = RoomStatus.ENDED
        ended_room.save(update_fields=["status"])
        request = RequestFactory().post("/")
        request.user = new_author
        space.author = new_author

        SpaceAdmin(type(space), AdminSite()).save_model(request, space, None, True)

        assert not Room.objects.filter(session=no_room_session).exists()
        ended_room.refresh_from_db()
        assert ended_room.keeper == old_author.slug
        assert ended_room.state_version == 0
        assert not RoomEventLog.objects.filter(room=ended_room).exists()

    def test_saving_unchanged_author_does_not_update_existing_room(self, db) -> None:
        author = UserFactory()
        space = SpaceFactory(author=author)
        session = SessionFactory(space=space)
        room = Room.objects.get_or_create_for_session(session)
        request = RequestFactory().post("/")
        request.user = author

        with patch("totem.rooms.state_machine.publish_state") as publish_state:
            SpaceAdmin(type(space), AdminSite()).save_model(request, space, None, True)

        room.refresh_from_db()
        assert room.keeper == author.slug
        assert room.state_version == 0
        assert not RoomEventLog.objects.filter(room=room).exists()
        publish_state.assert_not_called()


class TestSessionAdmin:
    def test_blank_prompt_inline_row_is_ignored(self):
        form = SessionPromptInlineForm(
            data={"prompt": "", "position": "1"},
            empty_permitted=True,
            use_required_attribute=False,
        )

        assert not form.has_changed()
        assert form.is_valid()

    def test_change_page_shows_attendee_emails(self, admin_client):
        session = SessionFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        session.attendees.add(user1, user2)
        url = reverse("admin:spaces_session_change", kwargs={"object_id": session.pk})
        response = admin_client.get(url)
        assert response.status_code == 200
        assert user1.email in response.content.decode()
        assert user2.email in response.content.decode()

    def test_feedback_is_read_only_on_session(self, admin_client: Client) -> None:
        session = SessionFactory()
        user = UserFactory(name="Feedback author")
        SessionFeedback.objects.create(session=session, user=user, feedback="down")
        content = admin_client.get(reverse("admin:spaces_session_change", args=[session.pk])).content.decode()
        assert f'href="{reverse("admin:users_user_change", args=[user.pk])}">Feedback author</a>' in content
        assert 'name="feedback-0-DELETE"' not in content

    @pytest.mark.django_db
    def test_str_identifies_the_session(self) -> None:
        space = SpaceFactory(title="Quiet Space")
        start = datetime.datetime(2025, 1, 15, 12, tzinfo=datetime.UTC)
        titled = SessionFactory(space=space, title="Finding connection", start=start)
        untitled = SessionFactory(space=space, title="", start=start)
        with timezone.override(datetime.UTC):
            assert str(titled) == "Finding connection — Quiet Space — 2025-01-15 12:00 UTC"
            assert str(untitled) == "Quiet Space — 2025-01-15 12:00 UTC"

    def test_change_page_links_to_participants(self, admin_client):
        session = SessionFactory()
        url = reverse("admin:spaces_session_change", kwargs={"object_id": session.pk})
        response = admin_client.get(url)
        assert reverse("admin:spaces_session_participants", args=[session.pk]) in response.content.decode()

    def test_add_page_renders(self, admin_client):
        # The participants link can't be built before the session has a pk.
        assert admin_client.get(reverse("admin:spaces_session_add")).status_code == 200

    def test_add_page_allows_ordering_discussion_prompts(self, admin_client):
        response = admin_client.get(reverse("admin:spaces_session_add"))

        assert response.status_code == 200
        assert 'name="discussion_prompts-0-prompt"' not in response.content.decode()
        assert "add another discussion prompt" in response.content.decode().lower()
        assert "js/admin/session_prompt_order.js" in response.content.decode()

    @pytest.mark.django_db
    def test_started_session_prompts_can_be_reordered_in_admin(self, admin_client):
        session = SessionFactory()
        SessionPrompt.objects.create(session=session, prompt="Already prepared", position=1)
        room = Room.objects.get_or_create_for_session(session)
        room.status = RoomStatus.ACTIVE
        room.save(update_fields=["status"])

        response = admin_client.get(reverse("admin:spaces_session_change", args=[session.pk]))

        assert response.status_code == 200
        assert 'name="discussion_prompts-0-prompt"' in response.content.decode()
        assert "add another discussion prompt" in response.content.decode().lower()

    @pytest.mark.parametrize("action", ["unchanged", "reorder", "edit_other", "edit_active", "delete_active"])
    def test_saving_session_syncs_active_prompt(self, admin_client: Client, action: str) -> None:
        session = SessionFactory()
        active_prompt = SessionPrompt.objects.create(session=session, prompt="Active prompt", position=1)
        other_prompt = SessionPrompt.objects.create(session=session, prompt="Other prompt", position=2)
        room = Room.objects.get_or_create_for_session(session)
        room.status = RoomStatus.ACTIVE
        room.round_number = 2
        room.save()
        completed_round = SessionRound.objects.create(
            session=session,
            number=1,
            prompt="Historical prompt",
            prepared_prompt=active_prompt,
            state=SessionRoundState.COMPLETED,
        )
        active_round = SessionRound.objects.create(
            session=session, number=2, prompt=active_prompt.prompt, prepared_prompt=active_prompt
        )
        url = reverse("admin:spaces_session_change", args=[session.pk])
        response = admin_client.get(url)
        form = response.context["adminform"].form
        data = {name: form.initial.get(name, field.initial) for name, field in form.fields.items()}
        data = {name: value if value is not None else "" for name, value in data.items()}
        data.update(
            {
                "space": session.space_id,
                "start_0": session.start.strftime("%Y-%m-%d"),
                "start_1": session.start.strftime("%H:%M:%S"),
                "duration_minutes": session.duration_minutes,
                "seats": session.seats,
                "discussion_prompts-TOTAL_FORMS": "2",
                "discussion_prompts-INITIAL_FORMS": "2",
                "discussion_prompts-0-id": active_prompt.pk,
                "discussion_prompts-0-session": session.pk,
                "discussion_prompts-0-prompt": "Edited active" if action == "edit_active" else active_prompt.prompt,
                "discussion_prompts-0-position": "2" if action == "reorder" else "1",
                "discussion_prompts-1-id": other_prompt.pk,
                "discussion_prompts-1-session": session.pk,
                "discussion_prompts-1-prompt": "Edited other" if action == "edit_other" else other_prompt.prompt,
                "discussion_prompts-1-position": "1" if action == "reorder" else "2",
            }
        )
        if action == "delete_active":
            data["discussion_prompts-0-DELETE"] = "on"
        for inline in response.context["inline_admin_formsets"]:
            prefix = inline.formset.prefix
            if prefix != "discussion_prompts":
                data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})

        response = admin_client.post(url, data)

        assert response.status_code == 302, response.context["errors"]
        active_round.refresh_from_db()
        room.refresh_from_db()
        completed_round.refresh_from_db()
        expected_prompt = {"edit_active": "Edited active", "delete_active": ""}.get(action, "Active prompt")
        assert active_round.prompt == expected_prompt
        assert room.to_state().round_message == (expected_prompt or None)
        assert active_round.prepared_prompt_id == (None if action == "delete_active" else active_prompt.pk)
        assert room.state_version == (1 if action in {"edit_active", "delete_active"} else 0)
        assert completed_round.prompt == "Historical prompt"

    @pytest.mark.django_db
    def test_space_admin_session_inline_allows_prompts(self, admin_client):
        space = SpaceFactory()
        SessionFactory(space=space)
        response = admin_client.get(reverse("admin:spaces_space_change", args=[space.pk]))

        assert response.status_code == 200
        assert 'name="sessions-0-discussion_prompts"' not in response.content.decode()

    def test_copy_session_copies_discussion_prompts(self, admin_client):
        session = SessionFactory()
        SessionPrompt.objects.create(session=session, prompt="First", position=1)
        SessionPrompt.objects.create(session=session, prompt="Second", position=2)

        response = admin_client.post(
            reverse("admin:spaces_session_changelist"),
            {"action": "copy_session", "_selected_action": [session.pk]},
        )

        assert response.status_code == 302
        copied_session = Session.objects.exclude(pk=session.pk).get(space=session.space)
        assert list(copied_session.discussion_prompts.values_list("prompt", flat=True)) == ["First", "Second"]


@pytest.mark.django_db
class TestSessionParticipantsView:
    def test_shows_participant_details(self, admin_client):
        session = SessionFactory()
        user = UserFactory(name="Claire")
        session.attendees.add(user)
        past = SessionFactory(start=timezone.now() - datetime.timedelta(days=7))
        past.attendees.add(user)
        past.joined.add(user)

        url = reverse("admin:spaces_session_participants", args=[session.pk])
        response = admin_client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Claire" in content
        assert user.email in content
        assert "100%" in content
        assert "1/1" in content

    def test_first_time_badge(self, admin_client):
        session = SessionFactory()
        session.attendees.add(UserFactory(name="Nate"))

        url = reverse("admin:spaces_session_participants", args=[session.pk])
        content = admin_client.get(url).content.decode()

        assert "First time" in content
        # Nobody with an empty record should be shown a meaningless "0% · 0/0".
        assert "No history" in content
        assert "0/0" not in content

    def test_missing_session_is_404(self, admin_client):
        url = reverse("admin:spaces_session_participants", args=[123456])
        assert admin_client.get(url).status_code == 404

    def test_staff_without_session_permission_is_404(self, client):
        session = SessionFactory()
        client.force_login(UserFactory(is_staff=True))
        url = reverse("admin:spaces_session_participants", args=[session.pk])
        assert client.get(url).status_code == 404

    def test_requires_staff(self, client):
        session = SessionFactory()
        client.force_login(UserFactory())
        url = reverse("admin:spaces_session_participants", args=[session.pk])
        response = client.get(url)
        assert response.status_code == 302
        assert "/admin/login/" in response.url


def ended_session(**kwargs) -> Session:
    kwargs.setdefault("start", timezone.now() - datetime.timedelta(days=1))
    return SessionFactory(**kwargs)


def give_feedback(session: Session, feedback: str, message: str = "", user: User | None = None) -> SessionFeedback:
    """Feedback from a participant who joined the session, so it counts toward the report."""
    user = user or UserFactory()
    session.joined.add(user)
    return SessionFeedback.objects.create(session=session, user=user, feedback=feedback, message=message)


@pytest.mark.django_db
class TestSessionFeedbackReport:
    url = reverse_lazy("admin:spaces_session_feedback_report")

    def test_space_change_page_links_to_filtered_report(self, admin_client: Client) -> None:
        space = SpaceFactory()
        give_feedback(ended_session(space=space), "up")
        give_feedback(ended_session(), "down")

        response = admin_client.get(reverse("admin:spaces_space_change", args=[space.pk]))
        report_url = f"{self.url}?space={space.pk}"
        assert response.status_code == 200
        assert f'href="{report_url}"' in response.content.decode()
        report = admin_client.get(report_url)
        assert report.status_code == 200
        assert report.context["totals"]["total"] == 1
        assert report.context["totals"]["positive"] == 1

    def test_totals_breakdowns_and_filters(self, admin_client: Client) -> None:
        first_space = SpaceFactory(title="First space")
        second_space = SpaceFactory(title="Second space")
        first = SessionFactory(space=first_space, start=datetime.datetime(2025, 1, 15, 20, tzinfo=datetime.UTC))
        second = SessionFactory(space=second_space, start=datetime.datetime(2025, 2, 15, 20, tzinfo=datetime.UTC))
        give_feedback(first, "up")
        give_feedback(first, "down")
        give_feedback(second, "up")

        response = admin_client.get(self.url)
        assert response.context["totals"] == {
            "positive": 2,
            "negative": 1,
            "total": 3,
            "positive_percent": 200 / 3,
            "negative_percent": 100 / 3,
        }
        assert [row["session__space__title"] for row in response.context["by_space"]] == ["First space", "Second space"]
        assert [(row["month"].month, row["total"]) for row in response.context["by_month"]] == [(1, 2), (2, 1)]
        response = admin_client.get(
            self.url,
            {"start_date": "2025-01-15", "end_date": "2025-01-15", "space": first_space.pk, "session": first.pk},
        )
        assert response.context["totals"]["total"] == 2
        assert response.context["totals"]["positive_percent"] == 50
        response = admin_client.get(self.url, {"space": first_space.pk, "session": second.pk})
        assert response.context["totals"]["total"] == 0
        assert response.context["totals"]["positive_percent"] is None
        response = admin_client.get(self.url, {"start_date": "2025-02-01", "end_date": "2025-01-01"})
        assert not response.context["form"].is_valid()
        assert "Correct the filters to see the report." in response.content.decode()

    def test_counts_the_same_responses_as_the_analytics_export(self, admin_client: Client) -> None:
        start = datetime.datetime(2025, 3, 10, 20, tzinfo=datetime.UTC)
        session = SessionFactory(start=start)
        give_feedback(session, "up")
        give_feedback(session, "down", message="Counted concern")
        no_show = UserFactory()
        session.attendees.add(no_show)
        SessionFeedback.objects.create(session=session, user=no_show, feedback="down", message="No-show concern")
        give_feedback(session, "down", message="Keeper concern", user=session.space.author)
        give_feedback(SessionFactory(start=start, cancelled=True), "down", message="Cancelled concern")
        give_feedback(SessionFactory(start=timezone.now() + datetime.timedelta(days=1)), "up")

        response = admin_client.get(self.url)

        totals = response.context["totals"]
        assert (totals["positive"], totals["negative"]) == (1, 1)
        metrics = {
            metric.metric_name: metric.value
            for metric in session_metrics(period=ReportPeriod.calendar_year(2025, "UTC"), as_of=timezone.now())
        }
        assert totals["total"] == metrics["feedback_responses"]
        assert totals["positive"] == metrics["positive_feedback_responses"]
        content = response.content.decode()
        assert "Counted concern" in content
        for excluded in ("No-show concern", "Keeper concern", "Cancelled concern"):
            assert excluded not in content
        export = admin_client.get(self.url, {"export": "csv"})
        assert len(list(csv.DictReader(io.StringIO(export.content.decode())))) == 2

    def test_dates_use_the_viewers_timezone(self, admin_client: Client) -> None:
        # 03:00 UTC on Feb 1 is still the evening of Jan 31 for a viewer in Los Angeles.
        session = SessionFactory(start=datetime.datetime(2025, 2, 1, 3, tzinfo=datetime.UTC))
        give_feedback(session, "down", message="Late concern")
        admin_client.cookies["totem_timezone"] = "America/Los_Angeles"

        response = admin_client.get(self.url)
        assert [row["month"].month for row in response.context["by_month"]] == [1]
        content = response.content.decode()
        assert "31st Jan 2025 7PM PST" in content
        assert "your timezone (America/Los_Angeles)" in content
        assert admin_client.get(self.url, {"end_date": "2025-01-31"}).context["totals"]["total"] == 1
        assert admin_client.get(self.url, {"start_date": "2025-02-01"}).context["totals"]["total"] == 0
        export = admin_client.get(self.url, {"export": "csv"})
        (row,) = csv.DictReader(io.StringIO(export.content.decode()))
        assert row["date"] == "2025-01-31T19:00:00-08:00"

        admin_client.cookies["totem_timezone"] = "UTC"
        assert [row["month"].month for row in admin_client.get(self.url).context["by_month"]] == [2]

    def test_downvote_messages_follow_report_filters(self, admin_client: Client) -> None:
        first = ended_session(title="Finding connection")
        user = UserFactory()
        give_feedback(first, "down", message="First concern", user=user)
        give_feedback(ended_session(), "down", message="Other concern")
        give_feedback(first, "up", message="Positive comment")

        content = admin_client.get(self.url, {"session": first.pk}).content.decode()

        assert f'href="{reverse("admin:users_user_change", args=[user.pk])}">{escape(user.name)}</a>' in content
        assert f'href="{reverse("admin:spaces_session_change", args=[first.pk])}">Finding connection</a>' in content
        assert "First concern" in content
        assert "Other concern" not in content
        assert "Positive comment" not in content

    def test_downvote_messages_are_paginated_without_limiting_totals_or_export(self, admin_client: Client) -> None:
        session = ended_session()
        users = [UserFactory(email=f"respondent{i}@example.com") for i in range(201)]
        session.joined.add(*users)
        SessionFeedback.objects.bulk_create(
            [
                SessionFeedback(session=session, user=user, feedback="down", message=f"Concern {i}")
                for i, user in enumerate(users)
            ]
        )

        response = admin_client.get(self.url, {"session": session.pk})
        assert response.context["totals"]["negative"] == 201
        messages = list(response.context["downvotes"])
        assert len(messages) == 200
        assert messages[0].message == "Concern 200"
        assert messages[-1].message == "Concern 1"
        content = response.content.decode()
        assert f'href="?session={session.pk}&amp;messages_page=2#feedback-messages"' in content
        assert "Previous" not in content

        response = admin_client.get(self.url, {"session": session.pk, "messages_page": 2})
        assert [item.message for item in response.context["downvotes"]] == ["Concern 0"]
        assert response.context["totals"]["negative"] == 201
        content = response.content.decode()
        assert f'href="?session={session.pk}&amp;messages_page=1#feedback-messages"' in content
        assert "messages_page=3" not in content

        export = admin_client.get(self.url, {"session": session.pk, "export": "csv"})
        assert len(list(csv.DictReader(io.StringIO(export.content.decode())))) == 201

    def test_export_includes_filtered_responses(self, admin_client: Client) -> None:
        session = ended_session(title="A session")
        user = UserFactory()
        give_feedback(session, "down", message="=1+1", user=user)
        give_feedback(session, "up")
        give_feedback(ended_session(), "down", message="Other")
        response = admin_client.get(self.url, {"session": session.pk, "export": "csv"})

        assert response["Content-Type"].startswith("text/csv")
        assert "attachment" in response["Content-Disposition"]
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        assert len(rows) == 2
        assert {row["feedback"] for row in rows} == {"up", "down"}
        downvote = next(row for row in rows if row["feedback"] == "down")
        assert downvote["session"] == "A session"
        assert downvote["user_name"] == user.name
        assert downvote["user_email"] == user.email
        assert downvote["message"] == "'=1+1"
        invalid = admin_client.get(self.url, {"export": "csv", "start_date": "invalid"})
        assert invalid["Content-Type"].startswith("text/html")
        assert not invalid.context["form"].is_valid()

    def test_session_filter_searches_through_admin_autocomplete(self, admin_client: Client) -> None:
        space = SpaceFactory(title="Quiet Space")
        session = SessionFactory(space=space, title="Finding connection")
        other = SessionFactory(title="Unrelated session")
        search_url = reverse("admin:autocomplete")

        content = admin_client.get(self.url).content.decode()
        assert f'data-ajax--url="{search_url}"' in content
        assert "Finding connection" not in content
        assert "Unrelated session" not in content
        response = admin_client.get(
            search_url,
            {"term": "Quiet Space", "app_label": "spaces", "model_name": "sessionfeedback", "field_name": "session"},
        )
        results = {result["id"]: result["text"] for result in response.json()["results"]}
        assert "Finding connection — Quiet Space" in results[str(session.pk)]
        assert str(other.pk) not in results
        response = admin_client.get(self.url, {"session": session.pk})
        assert "Finding connection — Quiet Space" in response.content.decode()
        assert response.context["form"].is_valid()

    def test_tools_index_links_to_report(self, admin_client: Client) -> None:
        assert f'href="{self.url}"' in admin_client.get(reverse("admin:index")).content.decode()

    def test_report_requires_session_view_permission(self, client: Client) -> None:
        user = UserFactory(is_staff=True, is_superuser=False)
        client.force_login(user)
        assert client.get(self.url).status_code == 404
        assert client.get(self.url, {"export": "csv"}).status_code == 404
