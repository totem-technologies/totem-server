"""Tests for per-view CSP override behavior.

The site policy lives in settings (SECURE_CSP / SECURE_CSP_REPORT_ONLY);
the proxied views (marketing site, Flutter room app) serve third-party
HTML that can't carry our nonces, so they replace the policy with a
view-specific one via csp_override_from_settings.
"""

from unittest.mock import patch

import pytest
from django.http import HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.utils.csp import CSP

from totem.conftest import fake_upstream as _fake_upstream
from totem.users.tests.factories import UserFactory
from totem.utils.csp import csp_override_from_settings

RO_HEADER = "Content-Security-Policy-Report-Only"
ENFORCE_HEADER = "Content-Security-Policy"

_SITE_POLICY = {"script-src": [CSP.SELF, CSP.NONCE]}
_OVERRIDE_POLICY = {"script-src": [CSP.SELF, CSP.UNSAFE_INLINE, CSP.WASM_UNSAFE_EVAL]}


@csp_override_from_settings("CSP_TEST_OVERRIDE")
def _view(request):
    return HttpResponse("ok")


def _get(settings_overrides: dict) -> HttpResponse:
    with override_settings(**settings_overrides):
        return _view(RequestFactory().get("/"))


def test_override_follows_report_only_mode():
    response = _get({"SECURE_CSP_REPORT_ONLY": _SITE_POLICY, "CSP_TEST_OVERRIDE": _OVERRIDE_POLICY})
    assert response._csp_ro_config == _OVERRIDE_POLICY
    assert not hasattr(response, "_csp_config")


def test_override_follows_enforce_mode():
    response = _get({"SECURE_CSP": _SITE_POLICY, "CSP_TEST_OVERRIDE": _OVERRIDE_POLICY})
    assert response._csp_config == _OVERRIDE_POLICY
    assert not hasattr(response, "_csp_ro_config")


def test_override_applies_to_both_modes_when_both_configured():
    response = _get(
        {
            "SECURE_CSP": _SITE_POLICY,
            "SECURE_CSP_REPORT_ONLY": _SITE_POLICY,
            "CSP_TEST_OVERRIDE": _OVERRIDE_POLICY,
        }
    )
    assert response._csp_config == _OVERRIDE_POLICY
    assert response._csp_ro_config == _OVERRIDE_POLICY


def test_empty_override_setting_leaves_site_policy():
    """An empty override dict (the non-production default) is a no-op."""
    response = _get({"SECURE_CSP_REPORT_ONLY": _SITE_POLICY, "CSP_TEST_OVERRIDE": {}})
    assert not hasattr(response, "_csp_ro_config")
    assert not hasattr(response, "_csp_config")


def test_no_site_policy_means_no_override():
    """If CSP isn't configured at all (dev), the override must not force headers on."""
    response = _get({"CSP_TEST_OVERRIDE": _OVERRIDE_POLICY})
    assert not hasattr(response, "_csp_ro_config")
    assert not hasattr(response, "_csp_config")


# ---------------------------------------------------------------------------
# End-to-end through the middleware: the proxied views get their own policy,
# regular pages get the site policy with a real nonce.
# ---------------------------------------------------------------------------


@override_settings(
    SECURE_CSP_REPORT_ONLY=_SITE_POLICY,
    CSP_ROOM_OVERRIDE=_OVERRIDE_POLICY,
)
def test_room_proxy_gets_override_policy(client: Client, db):
    user = UserFactory()
    client.force_login(user)
    with patch(
        "totem.rooms.proxy._session.request",
        return_value=_fake_upstream(200, b"<html>app</html>", "text/html"),
    ):
        response = client.get("/room/some-room")
    assert "wasm-unsafe-eval" in response.headers[RO_HEADER]
    assert "nonce-" not in response.headers[RO_HEADER]


@override_settings(
    SECURE_CSP_REPORT_ONLY=_SITE_POLICY,
    CSP_PROXIED_SITE_OVERRIDE={"script-src": [CSP.SELF, CSP.UNSAFE_INLINE]},
)
def test_marketing_proxy_gets_override_policy(client: Client):
    with patch("totem.pages.views.get_proxied_site_page", return_value="<html>marketing</html>"):
        response = client.get("/")
    assert "'unsafe-inline'" in response.headers[RO_HEADER]
    assert "nonce-" not in response.headers[RO_HEADER]


# ---------------------------------------------------------------------------
# Inert content (JSON, images, CSS, …): scripts can't run there, so the full
# site policy (nonce and all) is dead weight. The inert_csp middleware swaps
# in a minimal enforced policy and drops report-only.
# ---------------------------------------------------------------------------


def _response_for(content_type: str) -> HttpResponse:
    from totem.utils.middleware import inert_csp

    middleware = inert_csp(lambda request: HttpResponse(b"", content_type=content_type))
    return middleware(RequestFactory().get("/thing"))


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/json; charset=utf-8",
        "application/problem+json",
        "text/plain",
        "text/csv",
        "text/css",
        "application/wasm",
        "font/woff2",
        "image/jpeg",
        "image/png",
        "image/webp",
    ],
)
def test_inert_content_gets_minimal_enforced_policy(content_type: str):
    response = _response_for(content_type)
    assert response._csp_config == {"default-src": [CSP.NONE], "frame-ancestors": [CSP.NONE]}
    assert response._csp_ro_config == {}


@pytest.mark.parametrize(
    "content_type",
    [
        "text/html",
        "text/html; charset=utf-8",
        # Documents that can run scripts must keep the site policy. SVG is
        # the classic trap: it's an "image" that executes <script>.
        "image/svg+xml",
        "application/xhtml+xml",
        "application/xml",
        "application/pdf",
        # Worker scripts are governed by the CSP served with the script
        # response itself, not the document's — a minimal policy here would
        # cut off any same-origin worker's network access.
        "text/javascript",
        "application/javascript",
    ],
)
def test_scriptable_content_keeps_site_policy(content_type: str):
    response = _response_for(content_type)
    assert not hasattr(response, "_csp_config")
    assert not hasattr(response, "_csp_ro_config")


@override_settings(SECURE_CSP_REPORT_ONLY=_SITE_POLICY)
def test_api_route_headers_end_to_end(client: Client):
    """Through the full middleware stack: JSON gets the tiny enforced
    policy, no report-only header, and no nonce."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "Content-Security-Policy-Report-Only" not in response.headers


@override_settings(SECURE_CSP_REPORT_ONLY=_SITE_POLICY)
def test_regular_page_gets_site_policy_with_nonce(client: Client):
    response = client.get("/users/login/")
    assert response.status_code == 200
    header = response.headers[RO_HEADER]
    assert "nonce-" in header
    # The same nonce must be stamped on the page's inline scripts.
    nonce = header.split("nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"' in response.content.decode()
