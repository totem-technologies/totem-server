"""Tests for the /room/* reverse proxy.

These only cover the request-routing logic — we don't spin up an upstream
to test the proxying itself. The integration behavior (asset streaming,
base-href rewriting, conditional-header forwarding) is exercised manually
against the Flutter dev server.
"""

from unittest.mock import patch

import pytest
import requests
from django.test import Client, override_settings


def test_proxy_rejects_non_get(client: Client, db):
    """POST/PUT/etc. must not silently downgrade to GET upstream."""
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
    r.raw = type("R", (), {"stream": lambda self, *a, **kw: iter([body])})()
    return r


@override_settings(DEBUG=True)
def test_proxy_forwards_4xx_from_upstream(client: Client, db):
    """A 404 (or other 4xx) upstream is the asset's real status — the
    browser should see it, not a Django 500.
    """
    with patch("totem.rooms.proxy._session.request", return_value=_fake_upstream(404, b"nope")):
        response = client.get("/room/missing.js")
    assert response.status_code == 404


def test_proxy_raises_on_5xx_from_upstream(client: Client, db):
    """Upstream 5xx means *we* have a problem (CDN misconfig, origin down).
    Raise so Django returns 500 and Sentry alerts with request context.
    """
    with patch("totem.rooms.proxy._session.request", return_value=_fake_upstream(503, b"down")):
        with pytest.raises(requests.exceptions.HTTPError):
            client.get("/room/foo.js", raise_request_exception=True)


@override_settings(DEBUG=True)
def test_proxy_response_headers_allow_list(client: Client, db):
    """Upstream-sourced sensitive headers (Set-Cookie, HSTS, CSP, server
    info) must not survive the proxy; only the allow-listed caching/range
    headers come through.
    """
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


@override_settings(DEBUG=False)
def test_proxy_refuses_to_stream_assets_in_prod(client: Client, db):
    """In prod, assets must be served by the CDN — the proxy refusing to
    stream them guards against accidentally pointing prod traffic at a
    dev server.
    """
    fake = _fake_upstream(200, b"console.log('hi');", "application/javascript")
    with patch("totem.rooms.proxy._session.request", return_value=fake):
        with pytest.raises(Exception, match="Asset proxy should only be activated in dev"):
            client.get("/room/foo.js", raise_request_exception=True)
