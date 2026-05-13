"""Reverse proxy that mounts the Flutter web build under `/room/`.

In dev this points at `flutter run -d chrome`'s dev server (defaults to
`http://localhost:5173`). In prod it points at wherever the built Flutter
app is hosted (e.g. a Cloudflare Pages URL). Same code path either way.

What it does:
- Strips the `/room/` URL prefix before forwarding upstream.
- Streams binary responses so we don't buffer multi-MB wasm/js bundles.
- (dev only) Rewrites `<base href="/">` on HTML responses to
  `<base href="/room/">`. Flutter's `flutter run` dev server has no
  `--base-href` flag and always serves `<base href="/">`, which would
  send asset URLs and SPA routes to the wrong path. Prod builds with
  `--base-href=/room/` so the rewrite is unnecessary there.
- SPA fallback: for top-level HTML navigation to a path the upstream
  doesn't recognize (e.g. `/room/lobby`), serves index.html so the SPA
  router can resolve the path on the client.
- Forwards conditional-request headers so soft refreshes hit 304 Not
  Modified instead of re-downloading the whole asset bundle.
- Overrides the upstream Host header so any URLs the upstream embeds
  (e.g. dwds dev-tooling) resolve from the browser.
"""

from __future__ import annotations

import requests
from django.conf import settings
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

# Single shared session so HTTP keep-alive to the upstream is reused
# across requests.
_session = requests.Session()


# Response headers we forward from upstream to the client. Allow-list
# instead of deny-list so a new sensitive upstream header (set-cookie, HSTS,
# CSP, server-info leak, etc.) doesn't get auto-forwarded. content-type is
# set explicitly on the response. content-length / transfer-encoding are
# recomputed by Django/granian. Everything not listed here is dropped.
_FORWARDED_RESPONSE_HEADERS = frozenset(
    h.lower()
    for h in (
        # Caching / conditional requests:
        "Cache-Control",
        "ETag",
        "Last-Modified",
        "Expires",
        "Age",
        "Vary",
        # Range / partial content:
        "Accept-Ranges",
        "Content-Range",
        # Content negotiation:
        "Content-Encoding",
        "Content-Language",
    )
)

# Request headers worth forwarding to the upstream. The conditional set is
# the important one: Flutter's dev server returns ETag with
# `Cache-Control: max-age=0, must-revalidate`, so without forwarding
# If-None-Match every refresh becomes a full re-download of all 100+ MB of
# DDC bundles instead of a 304.
_FORWARDED_REQUEST_HEADERS = (
    "Accept",
    "Accept-Language",
    "User-Agent",
    "If-None-Match",
    "If-Modified-Since",
    "Range",
)


def _is_spa_navigation(request: HttpRequest, path: str) -> bool:
    """A top-level HTML navigation to a non-asset path.

    Browsers set `Sec-Fetch-Mode: navigate` only for top-level navigations
    (URL bar, link click, history nav). Asset/fetch/XHR requests use
    different modes. Using this header means asset paths can never
    accidentally fall back to index.html.
    """
    if request.headers.get("Sec-Fetch-Mode") != "navigate":
        return False
    last = path.rsplit("/", 1)[-1]
    if "." in last:  # Path looks like a file — treat as asset.
        return False
    return True


def _build_upstream_url(path: str, query: str) -> str:
    # Base URL is fixed at startup from `ROOM_APP_PROXY_BASE_URL`. The user-
    # controlled `path` is appended after a literal `/`, which `requests`
    # treats as part of the path — it cannot escape to a different scheme,
    # host, or port. So although /room/<path> is unauthenticated and
    # publicly reachable, this proxy can only ever fetch from the configured
    # upstream. (`ROOM_APP_PROXY_BASE_URL` itself must never be set to an
    # internal service the public web shouldn't expose.)
    base = settings.ROOM_APP_PROXY_BASE_URL.rstrip("/")
    url = f"{base}/{path}" if path else f"{base}/"
    if query:
        url = f"{url}?{query}"
    return url


def _rewrite_dev_base_href(body: bytes) -> bytes:
    """Patch the dev server's `<base href="/">` so asset URLs and SPA
    routes resolve under `/room/`. Only useful in dev — prod builds with
    `--base-href=/room/` so the patterns won't match anyway, but we skip
    the scan entirely under non-DEBUG.
    """
    if not settings.DEBUG:
        return body
    return body.replace(b'<base href="/">', b'<base href="/room/">').replace(
        b'<base href="$FLUTTER_BASE_HREF">', b'<base href="/room/">'
    )


_ALLOWED_METHODS = ("GET", "HEAD")


@csrf_exempt
def room_app_proxy(request: HttpRequest, path: str = "") -> HttpResponse | StreamingHttpResponse:
    if request.method not in _ALLOWED_METHODS:
        return HttpResponse(status=405, headers={"Allow": ", ".join(_ALLOWED_METHODS)})

    upstream_path = "" if _is_spa_navigation(request, path) else path
    url = _build_upstream_url(upstream_path, request.META.get("QUERY_STRING", ""))

    forward_headers = {h: request.headers[h] for h in _FORWARDED_REQUEST_HEADERS if h in request.headers}
    forward_headers["Host"] = settings.ROOM_APP_PROXY_BROWSER_HOST

    # Upstream errors (timeout, connection refused, 5xx) propagate as
    # unhandled exceptions. Django's DjangoIntegration in Sentry captures
    # them with full request context, and Django shows the user its
    # standard 500 page. The (5, 60) tuple is connect/read; the long read
    # timeout is for multi-MB wasm/dart bundles.
    upstream = _session.request(
        request.method, url, headers=forward_headers, stream=True, timeout=(5, 60)
    )
    if 500 <= upstream.status_code < 600:
        # 4xx is forwarded — `404` from upstream means the asset genuinely
        # doesn't exist and the browser should see that. Only 5xx is an
        # internal problem we want to alert on.
        upstream.raise_for_status()

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")

    if content_type.startswith("text/html"):
        # `upstream.content` buffers the body so we can mutate the bytes for
        # the dev-only `<base href>` rewrite. HTML responses are tiny; do not
        # convert this to streaming or the rewrite stops working.
        body = _rewrite_dev_base_href(upstream.content)
        response = HttpResponse(body, status=upstream.status_code, content_type=content_type)
    else:
        response = StreamingHttpResponse(
            upstream.iter_content(chunk_size=64 * 1024),
            status=upstream.status_code,
            content_type=content_type,
        )

    for header, value in upstream.headers.items():
        if header.lower() in _FORWARDED_RESPONSE_HEADERS:
            response[header] = value

    return response
