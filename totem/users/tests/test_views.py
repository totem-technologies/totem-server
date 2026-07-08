import re
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.http import HttpResponseRedirect
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from totem.onboard.tests.factories import OnboardModelFactory
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import Feedback, LoginPin, User
from totem.users.tests.factories import KeeperProfileFactory, UserFactory
from totem.users.views import FEEDBACK_SUCCESS_MESSAGE

pytestmark = pytest.mark.django_db


def test_user_update_view(client):
    user = UserFactory(verified=True)
    client.force_login(user)
    response = client.get(reverse("users:profile"))
    assert response.status_code == 200
    response = client.post(
        reverse("users:profile"), {"email": "new@example.com", "name": "New Name", "timezone": "UTC"}
    )
    assert user.email != "new@example.com"
    assert response.status_code == 200  # Response shows success message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    user.refresh_from_db()
    assert user.email == "new@example.com"
    assert user.verified is False


class TestUserRedirectView:
    def test_get_redirect_url(self, client, db):
        user = UserFactory(onboarded=False)
        client.force_login(user)
        url = reverse("users:redirect")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("onboard:index")
        OnboardModelFactory(user=user, onboarded=True)
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("users:dashboard")

    def test_user_index_view_after_login_with_next(self, client, db):
        url = reverse("users:profile")
        user = UserFactory()
        client.force_login(user)
        s = client.session
        s["next"] = url
        s.save()
        response = client.get(reverse("users:index"))
        assert isinstance(response, HttpResponseRedirect)
        assert response.url == reverse("users:profile")

    def test_user_index_view_after_login_with_next_attacker(self, client, db):
        url = "https://attacker.com"
        user = UserFactory()
        client.force_login(user)
        s = client.session
        s["next"] = url
        s.save()
        response = client.get(reverse("users:index"))
        assert isinstance(response, HttpResponseRedirect)
        assert "attacker" not in response.url


class TestUserDetailView:
    def test_authenticated(self, user: User, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse("users:detail", kwargs={"slug": user.slug}))
        assert response.status_code == 404
        response = client.get(reverse("users:detail", kwargs={"slug": "notreal"}))
        assert response.status_code == 404
        keeper_profile = KeeperProfileFactory()
        response = client.get(reverse("users:detail", kwargs={"slug": keeper_profile.user.slug}))
        assert response.status_code == 200


class TestUserIndexView:
    def test_user_index_view(self, client, db):
        url = reverse("users:profile")
        response = client.get(url)
        assert isinstance(response, HttpResponseRedirect)
        assert response.url == reverse("users:login") + "?next=" + url

        url = reverse("users:index")
        user = UserFactory(onboarded=False)
        client.force_login(user)
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == "/onboard/"
        OnboardModelFactory(user=user, onboarded=True)
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == "/users/dashboard/"


class TestPinVerification:
    def test_verify_pin_success(self, client):
        user = UserFactory(verified=False)
        pin = LoginPin.objects.generate_pin(user)

        response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin.pin})
        assert response.status_code == 302
        assert response.url == reverse("users:redirect")

        user.refresh_from_db()
        assert user.verified is True

    def test_verify_pin_invalid(self, client):
        user = UserFactory(verified=False)
        LoginPin.objects.generate_pin(user)

        response = client.post(
            reverse("users:verify-pin"),
            {"email": user.email, "pin": "000000"},  # Wrong PIN
        )
        assert response.status_code == 200
        assert b"Invalid or expired verification code" in response.content

        user.refresh_from_db()
        assert user.verified is False

    def test_verify_pin_expired(self, client):
        user = UserFactory(verified=False)
        pin = LoginPin.objects.generate_pin(user)
        # Manually set expiration to the past
        pin.expires_at = timezone.now() - timedelta(minutes=30)
        pin.save()

        response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin.pin})
        assert response.status_code == 200
        assert b"Invalid or expired verification code" in response.content

        user.refresh_from_db()
        assert user.verified is False

    def test_verify_pin_nonexistent_user(self, client):
        response = client.post(reverse("users:verify-pin"), {"email": "nonexistent@example.com", "pin": "123456"})
        assert response.status_code == 200
        assert b"Invalid or expired verification code" in response.content


class UserProfileViewTest(TestCase):
    def setUp(self):
        self.user = user = UserFactory()
        space = SpaceFactory(author=user)
        event = SessionFactory(space=space)
        event.attendees.add(user)
        event.joined.add(user)
        space.subscribed.add(user)
        self.client.force_login(user)

    def test_user_profile_view(self):
        url = reverse("users:profile")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/profile.html")
        self.assertEqual(response.context["object"], self.user)
        self.assertEqual(len(response.context["subscribed_spaces"]), 1)
        self.assertEqual(len(response.context["session_history"]), 1)
        self.assertEqual(response.context["space_count"], 1)


class UserFeedbackViewTest(TestCase):
    def test_user_feedback_view_authenticated(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.post(reverse("users:feedback"), data={"message": "Test feedback"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 1)
        feedback = Feedback.objects.first()
        assert feedback
        self.assertEqual(feedback.user, user)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn(FEEDBACK_SUCCESS_MESSAGE, messages)

    def test_user_feedback_view_anonymous(self):
        response = self.client.post(reverse("users:feedback"), data={"message": "Test feedback"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 1)
        feedback = Feedback.objects.first()
        assert feedback
        self.assertIsNone(feedback.user)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn(FEEDBACK_SUCCESS_MESSAGE, messages)

    def test_user_feedback_view_invalid_form(self):
        response = self.client.post(reverse("users:feedback"), data={"message": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 0)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertNotIn(FEEDBACK_SUCCESS_MESSAGE, messages)

    @patch("totem.users.views.notify_slack")
    def test_user_feedback_notifies_feedback_channel(self, mock_notify_slack):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.post(reverse("users:feedback"), data={"message": "Test feedback"})
        self.assertEqual(response.status_code, 200)
        mock_notify_slack.assert_called_once()
        self.assertEqual(mock_notify_slack.call_args.kwargs["channel"], settings.SLACK_FEEDBACK_CHANNEL_ID)


class TestDashboard:
    def test_dashboard_200(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse("users:dashboard"))
        assert response.status_code == 200

    def test_dashboard_attending_session_has_actions(self, client):
        user = UserFactory()
        client.force_login(user)
        session = SessionFactory()
        session.add_attendee(user)
        response = client.get(reverse("users:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "t-add-to-calendar" in content
        assert "Give up spot" in content
        rsvp_url = reverse("spaces:rsvp", kwargs={"session_slug": session.slug})
        assert rsvp_url in content
        # the give-up form must carry a CSRF token ({% include ... only %} strips it)
        form = re.search(
            r'<form[^>]+action="' + re.escape(rsvp_url) + r'"[^>]*>(.*?)</form>',
            content,
            re.DOTALL,
        )
        assert form is not None
        assert "csrfmiddlewaretoken" in form.group(1)

    def test_dashboard_hero_shows_next_session(self, client):
        user = UserFactory()
        client.force_login(user)
        soon = SessionFactory(start=timezone.now() + timedelta(hours=2), title="Soonest Session")
        soon.add_attendee(user)
        later = SessionFactory(start=timezone.now() + timedelta(days=3), title="Later Session")
        later.add_attendee(user)
        response = client.get(reverse("users:dashboard"))
        content = response.content.decode()
        assert response.context["next_session"] == soon
        assert "Your next session" in content
        assert "t-session-countdown" in content
        # the hero session is not repeated in the day-grouped list
        groups = response.context["session_groups"]
        grouped_sessions = [s for g in groups for s in g.sessions]
        assert soon not in grouped_sessions
        assert later in grouped_sessions

    def test_dashboard_groups_sessions_by_day(self, client):
        user = UserFactory()
        client.force_login(user)
        # Fix "now" to midday UTC so offsets never cross a day boundary.
        fixed_now = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        with patch("django.utils.timezone.now", return_value=fixed_now):
            hero = SessionFactory(start=fixed_now + timedelta(hours=1))
            hero.add_attendee(user)
            today = SessionFactory(start=fixed_now + timedelta(hours=3))
            today.add_attendee(user)
            tomorrow = SessionFactory(start=fixed_now + timedelta(days=1))
            tomorrow.add_attendee(user)
            later = SessionFactory(start=fixed_now + timedelta(days=10))
            later.add_attendee(user)
            response = client.get(reverse("users:dashboard"))
        groups = response.context["session_groups"]
        labels = [g.label for g in groups]
        assert labels[0] == "Today"
        assert labels[1] == "Tomorrow"
        assert len(labels) == 3
        assert groups[0].sessions == [today]
        assert groups[1].sessions == [tomorrow]
        assert groups[2].sessions == [later]

    def test_dashboard_empty_state(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse("users:dashboard"))
        content = response.content.decode()
        assert response.context["next_session"] is None
        assert "Find your people" in content
        assert reverse("spaces:list") in content


class TestDeleteUser:
    def test_delete_user(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.post(reverse("users:profile-delete"))
        assert response.status_code == 302
        assert response.url == reverse("pages:home")
        with pytest.raises(User.DoesNotExist):
            user.refresh_from_db()
