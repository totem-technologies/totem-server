from unittest import mock

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponseRedirect
from django.test import RequestFactory
from django.urls import reverse
from sesame.utils import get_query_string

from totem.onboard.models import OnboardModel
from totem.users.models import User
from totem.users.tests.factories import UserFactory
from totem.users.views import MagicLoginView, user_detail_view, user_redirect_view, user_update_view

from ..views import user_index_view

pytestmark = pytest.mark.django_db


def test_user_update_view():
    factory = RequestFactory()
    user = UserFactory(verified=True)
    request = factory.get(reverse("users:update"))
    request.user = user
    middleware = SessionMiddleware(mock.MagicMock())
    middleware.process_request(request)
    request.session.save()
    response = user_update_view(request)
    assert response.status_code == 200

    request = factory.post(reverse("users:update"), {"email": "new@example.com"})
    assert user.email != "new@example.com"
    request.user = user
    middleware = SessionMiddleware(mock.MagicMock())
    middleware.process_request(request)
    request.session.save()
    messages = FallbackStorage(request)
    request._messages = messages
    response = user_update_view(request)
    assert response.status_code == 302
    assert response.url == f"/users/{user.pk}/"
    assert len(messages) is 1
    user.refresh_from_db()
    assert user.email == "new@example.com"
    assert user.verified == False


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
        assert response.url == reverse("users:detail", kwargs={"pk": user.pk})


class TestUserDetailView:
    def test_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = UserFactory()
        response = user_detail_view(request, pk=user.pk)

        assert response.status_code == 200

    def test_not_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = AnonymousUser()
        response = user_detail_view(request, pk=user.pk)
        login_url = reverse(settings.LOGIN_URL)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code == 302
        assert response.url == f"{login_url}?next=/fake-url/"


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
    assert response.url == f"/users/{user.pk}/"


def test_magic_login_view():
    factory = RequestFactory()
    user = UserFactory()
    user.verified = False
    user.save()
    qs = get_query_string(user)
    request = factory.get(reverse("magic-login") + qs)
    request.user = user
    middleware = SessionMiddleware(mock.MagicMock())
    middleware.process_request(request)
    request.session.save()
    messages = FallbackStorage(request)
    request._messages = messages
    response = MagicLoginView.as_view()(request)
    assert response.status_code == 302
    # assert response.url == reverse("login")
    assert len(messages) is 1
    user.refresh_from_db()
    assert user.verified == True

    user.verified = True
    user.save()
    qs = get_query_string(user)
    request = factory.get(reverse("magic-login") + qs)
    request.user = user
    middleware = SessionMiddleware(mock.MagicMock())
    middleware.process_request(request)
    request.session.save()
    messages = FallbackStorage(request)
    request._messages = messages
    response = MagicLoginView.as_view()(request)
    assert response.status_code == 302
    assert len(get_messages(request)) == 0
    user.refresh_from_db()
    assert user.verified == True
