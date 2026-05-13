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

import logging

import requests
from django.conf import settings
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse

logger = logging.getLogger(__name__)

_session = requests.Session()

# Hop-by-hop headers we never forward in either direction (RFC 7230 §6.1),
# plus content-length which Django/granian recompute from the body.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
}

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


def room_app_proxy(request: HttpRequest, path: str = "") -> HttpResponse | StreamingHttpResponse:
    upstream_path = "" if _is_spa_navigation(request, path) else path
    url = _build_upstream_url(upstream_path, request.META.get("QUERY_STRING", ""))

    forward_headers = {h: request.headers[h] for h in _FORWARDED_REQUEST_HEADERS if h in request.headers}
    forward_headers["Host"] = settings.ROOM_APP_PROXY_BROWSER_HOST

    try:
        upstream = _session.get(url, headers=forward_headers, stream=True, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.warning("Room app proxy upstream error fetching %s: %s", url, e)
        return HttpResponse(
            f"Room app upstream unavailable: {e}",
            status=502,
            content_type="text/plain",
        )

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")

    if content_type.startswith("text/html"):
        body = _rewrite_dev_base_href(upstream.content)
        response = HttpResponse(body, status=upstream.status_code, content_type=content_type)
    else:
        response = StreamingHttpResponse(
            upstream.iter_content(chunk_size=64 * 1024),
            status=upstream.status_code,
            content_type=content_type,
        )

    skip = _HOP_BY_HOP | {"content-type"}
    for header, value in upstream.headers.items():
        if header.lower() in skip:
            continue
        response[header] = value

    return response
