"""Tests for the /room/* reverse proxy.

These only cover the request-routing logic — we don't spin up an upstream
to test the proxying itself. The integration behavior (asset streaming,
base-href rewriting, conditional-header forwarding) is exercised manually
against the Flutter dev server.
"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from django.middleware.security import SecurityMiddleware
from django.test import Client, override_settings
from django.urls import reverse

from totem.rooms.proxy import room_app_proxy
from totem.users.tests.factories import UserFactory


def test_room_root_redirects_to_home(client: Client, db):
    """The bare /room/ URL has no room context so it always redirects to the home page"""
    response = client.get("/room/")
    assert response.status_code == 302
    assert response.url == reverse("pages:home")


def test_proxy_redirects_unauthenticated_to_login(client: Client, db):
    """Unauthenticated requests to /room/ must redirect to login with
    a `next` parameter pointing back to the original URL."""
    response = client.get("/room/some-room-slug")
    assert response.status_code == 302
    parsed = urlparse(response.url)
    qs = parse_qs(parsed.query)
    assert "next" in qs
    assert qs["next"][0] == "/room/some-room-slug"


@override_settings(DEBUG=True)
def test_authenticated_user_can_access_room_after_login(client: Client, db):
    """After logging in, the user must be able to reach the original /room/ URL they were trying to access."""
    original_url = "/room/some-room-slug"

    # unauthenticated request gets redirected to login
    response = client.get(original_url)
    assert response.status_code == 302
    parsed = urlparse(response.url)
    qs = parse_qs(parsed.query)
    assert qs["next"][0] == original_url

    # simulate login and re-request the original URL. now it should reach the proxy
    user = UserFactory()
    client.force_login(user)

    with patch(
        "totem.rooms.proxy._session.request",
        return_value=_fake_upstream(200, b"<html><body>Flutter App</body></html>", "text/html"),
    ):
        response = client.get(original_url)
    assert response.status_code == 200
    assert b"Flutter App" in response.content


def test_proxy_rejects_non_get(client: Client, db):
    """POST/PUT/etc. must not silently downgrade to GET upstream."""
    user = UserFactory()
    client.force_login(user)
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/room/something")
        assert response.status_code == 405, f"{method} should 405"
        allow = response.headers["Allow"]
        assert "GET" in allow and method.upper() not in allow


def _fake_upstream(status: int, body: bytes = b"", content_type: str = "text/plain") -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = body
    r.headers["Content-Type"] = content_type
    r.raw = BytesIO(body)
    return r


@pytest.mark.parametrize(
    ("debug", "alias"),
    [(False, None), (True, None), (False, "pr-166-video-experience")],
    ids=["production", "development", "preview"],
)
@pytest.mark.parametrize("method", ["get", "head"])
def test_room_html_cross_origin_isolation(rf, settings, debug, alias, method):
    settings.DEBUG = debug
    settings.ROOM_PREVIEW_ENABLED = alias is not None
    request = getattr(rf, method)("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
    request.user = SimpleNamespace(is_authenticated=True)
    request.session = {}
    fake = _fake_upstream(200, b"<html>Flutter</html>", "text/html; charset=utf-8")
    fake.headers.update({"Cross-Origin-Opener-Policy": "unsafe-none", "Cross-Origin-Embedder-Policy": "require-corp"})

    with (
        patch("totem.rooms.proxy._session.request", return_value=fake),
        patch("totem.rooms.proxy.selected_alias", return_value=alias),
    ):
        response = SecurityMiddleware(lambda req: room_app_proxy(req, path="lobby"))(request)

    assert response.status_code == 200
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response["Cross-Origin-Embedder-Policy"] == "credentialless"


@override_settings(DEBUG=True, ROOM_PREVIEW_ENABLED=False)
@pytest.mark.django_db
def test_room_asset_does_not_receive_cross_origin_embedder_policy(rf):
    request = rf.get("/room/main.dart.js")
    request.user = SimpleNamespace(is_authenticated=True)
    request.session = {}
    fake = _fake_upstream(200, b"void 0;", "application/javascript")
    fake.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

    with patch("totem.rooms.proxy._session.request", return_value=fake):
        response = room_app_proxy(request, path="main.dart.js")

    try:
        assert response.status_code == 200
        assert "Cross-Origin-Embedder-Policy" not in response.headers
    finally:
        response.close()


@override_settings(DEBUG=True)
def test_proxy_forwards_4xx_from_upstream(client: Client, db):
    """A 404 (or other 4xx) upstream is the asset's real status — the
    browser should see it, not a Django 500.
    """
    user = UserFactory()
    client.force_login(user)
    with patch("totem.rooms.proxy._session.request", return_value=_fake_upstream(404, b"nope")):
        response = client.get("/room/missing.js")
    assert response.status_code == 404


def test_proxy_raises_on_5xx_from_upstream(client: Client, db):
    """Upstream 5xx means *we* have a problem (CDN misconfig, origin down).
    Raise so Django returns 500 and Sentry alerts with request context.
    """
    user = UserFactory()
    client.force_login(user)
    with patch("totem.rooms.proxy._session.request", return_value=_fake_upstream(503, b"down")):
        with pytest.raises(requests.exceptions.HTTPError):
            client.get("/room/foo.js", raise_request_exception=True)


@override_settings(DEBUG=True)
@pytest.mark.django_db
def test_proxy_response_headers_allow_list(client: Client, db):
    """Upstream-sourced sensitive headers (Set-Cookie, HSTS, CSP, server
    info) must not survive the proxy; only the allow-listed caching/range
    headers come through.
    """
    user = UserFactory()
    client.force_login(user)
    fake = _fake_upstream(200, b"console.log('hi');", "application/javascript")
    fake.headers.update(
        {
            "Cache-Control": "max-age=3600",
            "ETag": '"abc123"',
            # These must all be dropped:
            "Set-Cookie": "evil_session=1",
            "Strict-Transport-Security": "max-age=31536000",
            "Content-Security-Policy": "default-src 'none'",
            "Server": "leak/1.0",
            "X-Powered-By": "leak",
        }
    )

    with patch("totem.rooms.proxy._session.request", return_value=fake):
        response = client.get("/room/foo.js")

    # Allow-list passes through:
    assert response["Cache-Control"] == "max-age=3600"
    assert response["ETag"] == '"abc123"'
    # Drops the rest:
    assert "Set-Cookie" not in response.headers
    assert "Strict-Transport-Security" not in response.headers
    assert "Content-Security-Policy" not in response.headers
    assert "Server" not in response.headers or "leak" not in response["Server"]
    assert "X-Powered-By" not in response.headers


@override_settings(DEBUG=True, ROOM_APP_PROXY_BROWSER_HOST="cf-pages.totem.org")
def test_proxy_sets_host_header_to_browser_host(client: Client, db):
    """The upstream Host header is `ROOM_APP_PROXY_BROWSER_HOST`, not the
    request's own host. In dev this differs from the server-reachable
    `ROOM_APP_PROXY_BASE_URL` host (the docker-internal vs. browser split);
    in prod it must be set to match the upstream's public hostname so the
    CDN routes the request and embedded URLs resolve.
    """
    user = UserFactory()
    client.force_login(user)
    captured: dict[str, str] = {}

    def fake_request(method, url, *, headers, **kwargs):
        captured.update(headers)
        return _fake_upstream(200, b"<html></html>", "text/html")

    with patch("totem.rooms.proxy._session.request", side_effect=fake_request):
        client.get("/room/index.html")

    assert captured["Host"] == "cf-pages.totem.org"


@override_settings(DEBUG=False)
def test_proxy_refuses_to_stream_assets_in_prod(client: Client, db):
    """In prod, assets must be served by the CDN — the proxy refusing to
    stream them guards against accidentally pointing prod traffic at a
    dev server.
    """
    user = UserFactory()
    client.force_login(user)
    fake = _fake_upstream(200, b"console.log('hi');", "application/javascript")
    with patch("totem.rooms.proxy._session.request", return_value=fake):
        with pytest.raises(Exception, match="Asset proxy should only be activated in dev"):
            client.get("/room/foo.js", raise_request_exception=True)


@pytest.mark.django_db
class TestRoomPreviewProxy:
    alias = "pr-166-video-experience"
    host = "pr-166-video-experience-totem-web-preview.lopkerk.workers.dev"

    @pytest.fixture(autouse=True)
    def authenticated(self, client, settings):
        settings.ROOM_PREVIEW_ENABLED = True
        settings.DEBUG = False
        settings.ROOM_APP_PROXY_BASE_URL = "https://normal.lopkerk.workers.dev"
        settings.ROOM_APP_PROXY_BROWSER_HOST = "normal.lopkerk.workers.dev"
        client.force_login(UserFactory())

    def test_selected_origin_and_host(self, client):
        client.get("/room/lobby", {"room_preview": self.alias})
        fake = _fake_upstream(200, b"<html><body>Flutter</body></html>", "text/html")
        with patch("totem.rooms.proxy._session.request", return_value=fake) as upstream:
            response = client.get(
                "/room/lobby?keep=yes", HTTP_SEC_FETCH_MODE="navigate", HTTP_AUTHORIZATION="Bearer private"
            )
        assert response.status_code == 200
        assert upstream.call_args.args == ("GET", f"https://{self.host}/?keep=yes")
        assert upstream.call_args.kwargs["headers"]["Host"] == self.host
        assert "Cookie" not in upstream.call_args.kwargs["headers"]
        assert "Authorization" not in upstream.call_args.kwargs["headers"]
        assert upstream.call_args.kwargs["allow_redirects"] is False
        assert response.content == fake.content

    def test_switch_reset_and_expiry_select_the_right_upstream(self, client):
        fake = _fake_upstream(200, b"<html><body>Flutter</body></html>", "text/html")
        with patch("totem.rooms.proxy._session.request", return_value=fake) as upstream:
            for alias in [self.alias, "pr-2-other"]:
                client.get("/room/lobby", {"room_preview": alias})
                client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
                assert upstream.call_args.args[1] == f"https://{alias}-totem-web-preview.lopkerk.workers.dev/"
            client.get("/room/lobby", {"room_preview": "off"})
            client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
            assert upstream.call_args.args[1] == "https://normal.lopkerk.workers.dev/"
            assert upstream.call_args.kwargs["headers"]["Host"] == "normal.lopkerk.workers.dev"
            client.get("/room/lobby", {"room_preview": self.alias})
            session = client.session
            session["room_preview"] = {"alias": self.alias, "expires_at": 0}
            session.save()
            client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
            assert upstream.call_args.args[1] == "https://normal.lopkerk.workers.dev/"

    @pytest.mark.parametrize("selected", [True, False])
    def test_html_cannot_reuse_validators_from_a_different_build(self, client, selected):
        if selected:
            client.get("/room/lobby", {"room_preview": self.alias})
        fake = _fake_upstream(200, b"<html><body>Flutter</body></html>", "text/html")
        fake.headers.update(
            {"Cache-Control": "public, max-age=86400", "ETag": '"old"', "Last-Modified": "yesterday", "Age": "100"}
        )
        with patch("totem.rooms.proxy._session.request", return_value=fake) as upstream:
            response = client.get(
                "/room/lobby",
                HTTP_SEC_FETCH_MODE="navigate",
                HTTP_IF_NONE_MATCH='"old"',
                HTTP_IF_MODIFIED_SINCE="yesterday",
                HTTP_RANGE="bytes=0-10",
            )
        for header in ["If-None-Match", "If-Modified-Since", "Range"]:
            assert header not in upstream.call_args.kwargs["headers"]
        for header in ["ETag", "Last-Modified", "Age"]:
            assert header not in response.headers
        assert "no-store" in response["Cache-Control"]
        assert "private" in response["Cache-Control"]
        assert "public" not in response["Cache-Control"]

    @pytest.mark.parametrize("status", [404, 410])
    def test_missing_preview_clears_selection_and_explains_recovery(self, client, status):
        client.get("/room/lobby", {"room_preview": self.alias})
        with patch("totem.rooms.proxy._session.request", return_value=_fake_upstream(status, b"gone")):
            response = client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
        assert response.status_code == 404
        assert b"Room preview unavailable" in response.content
        assert b"Reload to return to normal staging" in response.content
        assert "room_preview" not in client.session
        assert "_auth_user_id" in client.session
        assert "no-store" in response["Cache-Control"]

    def test_upstream_failures_do_not_clear_selection(self, client):
        client.get("/room/lobby", {"room_preview": self.alias})
        with patch("totem.rooms.proxy._session.request", return_value=_fake_upstream(503, b"down")):
            with pytest.raises(requests.HTTPError):
                client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
        assert client.session["room_preview"]["alias"] == self.alias

    def test_preview_redirect_is_not_followed(self, client):
        client.get("/room/lobby", {"room_preview": self.alias})
        fake = _fake_upstream(302)
        fake.headers["Location"] = "https://other.example"
        with patch("totem.rooms.proxy._session.request", return_value=fake) as upstream:
            response = client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
        assert upstream.call_args.kwargs["allow_redirects"] is False
        assert response.status_code == 502
        assert "Location" not in response
        assert client.session["room_preview"]["alias"] == self.alias

    def test_disabled_feature_ignores_saved_preview(self, client, settings):
        client.get("/room/lobby", {"room_preview": self.alias})
        settings.ROOM_PREVIEW_ENABLED = False
        fake = _fake_upstream(200, b"<html><body>Normal build</body></html>", "text/html")
        with patch("totem.rooms.proxy._session.request", return_value=fake) as upstream:
            response = client.get("/room/lobby", HTTP_SEC_FETCH_MODE="navigate")
        assert upstream.call_args.args[1] == "https://normal.lopkerk.workers.dev/"
        assert self.alias.encode() not in response.content
