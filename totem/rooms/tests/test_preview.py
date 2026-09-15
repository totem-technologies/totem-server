from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory
from django.urls import reverse

from totem.rooms.preview import RoomPreviewMiddleware
from totem.rooms.tests.test_proxy import _fake_upstream
from totem.users.models import LoginPin
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
ALIAS = "pr-166-video-experience"


@pytest.fixture(autouse=True)
def previews_enabled(settings):
    settings.ROOM_PREVIEW_ENABLED = True
    with patch("django.utils.timezone.now", return_value=NOW):
        yield


def test_selection_is_saved_before_login_and_stripped_from_redirect(client, settings):
    response = client.get("/room/lobby", {"room_preview": ALIAS, "keep": ["one", "two"]})
    assert response.status_code == 302
    assert response.url == "/room/lobby?keep=one&keep=two"
    assert "no-store" in response["Cache-Control"]
    assert client.session["room_preview"] == {
        "alias": ALIAS,
        "expires_at": (NOW + timedelta(hours=2)).timestamp(),
    }
    assert client.session.get_expiry_age() == settings.SESSION_COOKIE_AGE
    assert "_session_expiry" not in client.session

    login = client.get(response.url)
    assert parse_qs(urlparse(login.url).query)["next"] == ["/room/lobby?keep=one&keep=two"]


@pytest.mark.parametrize("path", ["/", "/room/", "/room/lobby"])
def test_selection_works_on_entry_paths(client, path):
    response = client.get(path, {"room_preview": ALIAS})
    assert response.status_code == 302
    assert response.url == path
    assert client.session["room_preview"]["alias"] == ALIAS


def test_preview_survives_real_pin_login(client):
    user = UserFactory()
    client.get("/room/lobby", {"room_preview": ALIAS})
    selection = client.session["room_preview"]
    anonymous_session = client.session.session_key

    client.post(reverse("users:login") + "?next=/room/lobby", {"email": user.email})
    pin = LoginPin.objects.get(user=user).pin
    response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin})

    assert response.status_code == 302
    assert response.url == "/room/lobby"
    assert client.session.session_key != anonymous_session
    assert client.session["room_preview"] == selection
    assert client.session["_auth_user_id"] == str(user.pk)


def test_expiry_does_not_slide_or_log_the_user_out(client, settings):
    user = UserFactory()
    client.force_login(user)
    client.get("/room/", {"room_preview": ALIAS})
    selection = client.session["room_preview"]

    fake = _fake_upstream(200, b"<html></html>", "text/html")
    with patch("totem.rooms.proxy._session.request", return_value=fake):
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(hours=1)):
            client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
        assert client.session["room_preview"] == selection

        with patch("django.utils.timezone.now", return_value=NOW + timedelta(hours=2)):
            client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
    assert "room_preview" not in client.session
    assert client.session["_auth_user_id"] == str(user.pk)
    assert client.session.get_expiry_age() == settings.SESSION_COOKIE_AGE


def test_explicit_selection_restarts_the_two_hour_timer(client):
    client.get("/room/", {"room_preview": ALIAS})
    with patch("django.utils.timezone.now", return_value=NOW + timedelta(hours=1)):
        client.get("/room/", {"room_preview": ALIAS})
    assert client.session["room_preview"]["expires_at"] == (NOW + timedelta(hours=3)).timestamp()


def test_reset_clears_only_preview_and_logout_clears_selection(client):
    client.force_login(UserFactory())
    client.get("/room/", {"room_preview": ALIAS})
    auth_user = client.session["_auth_user_id"]
    response = client.get("/room/", {"room_preview": "off", "keep": "yes"})
    assert response.url == "/room/?keep=yes"
    assert "no-store" in response["Cache-Control"]
    assert "room_preview" not in client.session
    assert client.session["_auth_user_id"] == auth_user
    client.get("/room/", {"room_preview": ALIAS})
    client.logout()
    assert "room_preview" not in client.session


@pytest.mark.parametrize(
    "alias",
    [
        "",
        "https://evil.example",
        "//evil.example",
        "pr-0-bad",
        "pr-1-A",
        "pr-1-bad.",
        "pr-1-trailing-",
        "pr-1-trailing\n",
        "pr-1-" + "a" * 41,
        [ALIAS, "off"],
    ],
)
def test_invalid_selection_is_rejected_without_replacing_current_preview(client, alias):
    client.get("/room/", {"room_preview": ALIAS})
    selection = client.session["room_preview"]
    response = client.get("/room/", {"room_preview": alias})
    assert response.status_code == 400
    assert "no-store" in response["Cache-Control"]
    assert client.session["room_preview"] == selection


def test_longest_valid_alias_is_accepted(client):
    alias = "pr-1-" + "a" * 40
    assert len(alias + "-totem-web-preview") == 63
    assert client.get("/room/", {"room_preview": alias}).status_code == 302
    assert client.session["room_preview"]["alias"] == alias


def test_post_does_not_change_selection(client):
    response = client.post(reverse("users:login") + f"?room_preview={ALIAS}", {})
    assert response.status_code == 200
    assert "room_preview" not in client.session


def test_disabled_previews_ignore_query_and_stored_selection(client, settings):
    client.get("/room/", {"room_preview": ALIAS})
    settings.ROOM_PREVIEW_ENABLED = False
    response = client.get("/room/", {"room_preview": "pr-2-other"})
    assert response.url == reverse("pages:home")
    assert client.session["room_preview"]["alias"] == ALIAS


def test_selection_is_isolated_between_sessions(client):
    client.get("/room/", {"room_preview": ALIAS})
    other = Client()
    other.get("/room/")
    assert "room_preview" not in other.session


@pytest.mark.parametrize("selection", ["bad", {}, {"alias": ALIAS, "expires_at": "bad"}])
def test_invalid_session_selection_is_discarded(client, selection):
    client.force_login(UserFactory())
    session = client.session
    session["room_preview"] = selection
    session.save()
    fake = _fake_upstream(200, b"<html></html>", "text/html")
    with patch("totem.rooms.proxy._session.request", return_value=fake):
        client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
    assert "room_preview" not in client.session


@pytest.mark.parametrize("path", ["/room/hash%23tag", "/room/query%3Fmark", "/room/percent%25", "/room/%252F"])
def test_selection_redirect_preserves_escaped_path(client: Client, path: str) -> None:
    response = client.get(path, {"room_preview": ALIAS, "keep": "yes"})
    assert response.status_code == 302
    assert response.url == f"{path}?keep=yes"


@pytest.mark.parametrize("alias, status", [(ALIAS, 302), ("invalid", 400)])
def test_selection_responses_have_security_headers(client: Client, settings, alias: str, status: int) -> None:
    settings.ROBOTS_NO_INDEX = True
    response = client.get("/room/lobby", {"room_preview": alias})
    assert response.status_code == status
    assert response["X-Frame-Options"] == settings.X_FRAME_OPTIONS
    assert "noindex" in response["X-Robots-Tag"]


def test_selection_does_not_bypass_cdn_guard(client: Client, settings) -> None:
    settings.STATIC_HOST = "testserver"
    settings.STATIC_URL = "http://testserver/static/"
    response = client.get("/room/lobby", {"room_preview": ALIAS})
    assert response.status_code == 404
    assert "room_preview" not in client.session


def test_unrelated_request_does_not_access_preview_session() -> None:
    request = RequestFactory().get("/unrelated/")
    request.session = SessionStore()

    def respond(request: HttpRequest) -> HttpResponse:
        return HttpResponse("OK")

    response = RoomPreviewMiddleware(respond)(request)
    assert response.status_code == 200
    assert not request.session.accessed
