import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.http import HttpResponseRedirect
from django.test import RequestFactory, TestCase
from django.urls import reverse
from sesame.utils import get_query_string

from totem.circles.tests.factories import CircleEventFactory, CircleFactory
from totem.onboard.models import OnboardModel
from totem.users.models import Feedback, User
from totem.users.tests.factories import KeeperProfileFactory, UserFactory
from totem.users.views import FEEDBACK_SUCCESS_MESSAGE, user_redirect_view

from ..views import user_index_view

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
    assert response.status_code == 200
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    user.refresh_from_db()
    assert user.email == "new@example.com"
    assert user.verified is False


class TestUserRedirectView:
    def test_get_redirect_url(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url")
        request.user = user
        response = user_redirect_view(request)
        assert response.status_code == 302
        assert response.url == reverse("onboard:index")
        OnboardModel.objects.create(user=user)
        user.onboard.onboarded = True
        response = user_redirect_view(request)
        assert response.status_code == 302
        assert response.url == reverse("users:dashboard")


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


def test_user_index_view():
    factory = RequestFactory()
    request = factory.get("/someroute")
    request.user = AnonymousUser()
    response = user_index_view(request)
    assert isinstance(response, HttpResponseRedirect)
    assert response.url == reverse("users:login") + "?next=/someroute"

    user = UserFactory()
    request.user = user
    response = user_index_view(request)
    assert response.status_code == 302
    assert response.url == "/onboard/"

    OnboardModel.objects.create(user=user)
    user.onboard.onboarded = True
    user.onboard.save()
    response = user_index_view(request)
    assert response.status_code == 302
    assert response.url == "/users/dashboard/"


def test_magic_login_view_verify_email(client):
    user = UserFactory()
    user.verified = False
    qs = get_query_string(user)
    response = client.get(reverse("magic-login") + qs)
    assert response.status_code == 302
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 0
    user.refresh_from_db()
    assert user.verified is True

    qs = get_query_string(user)
    response = client.get(reverse("magic-login") + qs)
    assert response.status_code == 302
    assert len(get_messages(response.wsgi_request)) == 0
    user.refresh_from_db()
    assert user.verified is True


class UserProfileImageViewTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_user_profile_image_view(self):
        url = reverse("users:profile-image")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/profile/_profile_image_edit.html")

        # Test POST request
        data = {"randomize": True}
        oldseed = self.user.profile_avatar_seed
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/profile/_profile_image_edit.html")
        self.user.refresh_from_db()
        assert oldseed != self.user.profile_avatar_seed


class UserProfileViewTest(TestCase):
    def setUp(self):
        self.user = user = UserFactory()
        circle = CircleFactory(author=user)
        event = CircleEventFactory(circle=circle)
        event.attendees.add(user)
        event.joined.add(user)
        circle.subscribed.add(user)
        self.client.force_login(user)

    def test_user_profile_view(self):
        url = reverse("users:profile")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/profile.html")
        self.assertEqual(response.context["object"], self.user)
        self.assertEqual(len(response.context["subscribed_circles"]), 1)
        self.assertEqual(len(response.context["circle_history"]), 1)
        self.assertEqual(response.context["circle_count"], 1)


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
