import datetime

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.rooms.models import Room
from totem.rooms.schemas import RoomStatus
from totem.spaces.admin import SessionPromptInlineForm
from totem.spaces.models import Session, SessionPrompt, SessionRound, SessionRoundState
from totem.users.tests.factories import UserFactory

from .factories import SessionFactory, SpaceFactory


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

    def test_feedback_cannot_be_deleted_from_session(self, admin_client: Client) -> None:
        from totem.spaces.models import SessionFeedback

        session = SessionFactory()
        feedback = SessionFeedback.objects.create(session=session, user=UserFactory(), feedback="down")
        response = admin_client.get(reverse("admin:spaces_session_change", args=[session.pk]))
        inline = next(
            inline for inline in response.context["inline_admin_formsets"] if inline.opts.model is SessionFeedback
        )
        prefix = inline.formset.prefix
        assert f'name="{prefix}-0-DELETE"' not in response.content.decode()

        formset = type(inline.formset)(
            data={
                f"{prefix}-TOTAL_FORMS": "1",
                f"{prefix}-INITIAL_FORMS": "1",
                f"{prefix}-0-id": str(feedback.pk),
                f"{prefix}-0-session": str(session.pk),
                f"{prefix}-0-DELETE": "on",
            },
            instance=session,
            prefix=prefix,
        )
        assert formset.is_valid(), formset.errors
        formset.save()
        assert SessionFeedback.objects.filter(pk=feedback.pk).exists()

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


@pytest.mark.django_db
class TestSessionFeedbackReport:
    def test_space_change_page_links_to_filtered_report(self, admin_client: Client) -> None:
        from totem.spaces.models import SessionFeedback

        space = SpaceFactory()
        session = SessionFactory(space=space)
        SessionFeedback.objects.create(session=session, user=UserFactory(), feedback="up")
        SessionFeedback.objects.create(session=SessionFactory(), user=UserFactory(), feedback="down")

        response = admin_client.get(reverse("admin:spaces_space_change", args=[space.pk]))
        report_url = f"{reverse('admin:spaces_session_feedback_report')}?space={space.pk}"
        assert response.status_code == 200
        assert f'href="{report_url}"' in response.content.decode()
        report = admin_client.get(report_url)
        assert report.status_code == 200
        assert report.context["totals"]["total"] == 1
        assert report.context["totals"]["positive"] == 1

    def test_totals_breakdowns_and_filters(self, admin_client):
        from totem.spaces.models import SessionFeedback

        first_space = SpaceFactory(title="First space")
        second_space = SpaceFactory(title="Second space")
        first = SessionFactory(space=first_space, start=datetime.datetime(2025, 1, 15, 12, tzinfo=datetime.UTC))
        second = SessionFactory(space=second_space, start=datetime.datetime(2025, 2, 15, 12, tzinfo=datetime.UTC))
        SessionFeedback.objects.create(session=first, user=UserFactory(), feedback="up")
        SessionFeedback.objects.create(session=first, user=UserFactory(), feedback="down")
        SessionFeedback.objects.create(session=second, user=UserFactory(), feedback="up")
        url = reverse("admin:spaces_session_feedback_report")

        response = admin_client.get(url)
        assert response.context["totals"] == {
            "positive": 2,
            "negative": 1,
            "total": 3,
            "positive_percent": 200 / 3,
            "negative_percent": 100 / 3,
        }
        assert len(response.context["by_space"]) == 2
        assert len(response.context["by_month"]) == 2
        response = admin_client.get(
            url, {"start_date": "2025-01-15", "end_date": "2025-01-15", "space": first_space.pk, "session": first.pk}
        )
        assert response.context["totals"]["total"] == 2
        assert response.context["totals"]["positive_percent"] == 50
        response = admin_client.get(url, {"space": first_space.pk, "session": second.pk})
        assert response.context["totals"]["total"] == 0
        assert response.context["totals"]["positive_percent"] is None
        response = admin_client.get(url, {"start_date": "2025-02-01", "end_date": "2025-01-01"})
        assert not response.context["form"].is_valid()

    def test_downvote_messages_follow_report_filters(self, admin_client):
        from totem.spaces.models import SessionFeedback

        first = SessionFactory(title="Finding connection")
        second = SessionFactory()
        user = UserFactory()
        SessionFeedback.objects.create(session=first, user=user, feedback="down", message="First concern")
        SessionFeedback.objects.create(session=second, user=UserFactory(), feedback="down", message="Other concern")
        SessionFeedback.objects.create(session=first, user=UserFactory(), feedback="up", message="Positive comment")
        url = reverse("admin:spaces_session_feedback_report")

        response = admin_client.get(url, {"session": first.pk})
        from django.utils.html import escape

        assert str(escape(str(user))) in response.content.decode()
        assert (
            f'href="{reverse("admin:spaces_session_change", args=[first.pk])}">Finding connection</a>'
            in response.content.decode()
        )
        assert "First concern" in response.content.decode()
        assert "Other concern" not in response.content.decode()
        assert "Positive comment" not in response.content.decode()

    def test_report_requires_session_view_permission(self, client):
        user = UserFactory(is_staff=True, is_superuser=False)
        client.force_login(user)
        assert client.get(reverse("admin:spaces_session_feedback_report")).status_code == 404
