import zoneinfo
from typing import TYPE_CHECKING

from django.conf import settings
from django.http import Http404, HttpRequest
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.csp import CSP

if TYPE_CHECKING:
    from totem.users.models import User


class EnsureCsrfCookie:
    """Always send the csrftoken cookie so the JS frontend can read it.

    Forms are submitted by JS (see assets/js/libs/bot.ts and postData.ts) which
    echoes the cookie value back as the CSRF token, and pages don't render a
    {% csrf_token %} tag. CSRF_COOKIE_HTTPONLY is False so the cookie is readable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        get_token(request)
        return self.get_response(request)


# Scripts can't run in a JSON document, so serve the OWASP-recommended
# minimal policy instead of the site one (which is ~1KB per response and
# mints a nonce nothing will use). Enforced directly — there's nothing a
# report-only trial run could break in JSON.
_JSON_CSP = {"default-src": [CSP.NONE], "frame-ancestors": [CSP.NONE]}


def json_csp(get_response):
    def middleware(request: HttpRequest):
        response = get_response(request)

        if response.get("Content-Type", "").startswith("application/json"):
            response._csp_config = _JSON_CSP
            response._csp_ro_config = {}

        return response

    return middleware


def robotnoindex(get_response):
    def middleware(request: HttpRequest):
        response = get_response(request)

        if settings.ROBOTS_NO_INDEX:
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet, notranslate, noimageindex"

        return response

    return middleware


class TimezoneMiddleware:
    """Set the timezone for the request based on the authenticated user's timezone or the timezone cookie."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname: zoneinfo.ZoneInfo | None = None
        detected_tzname: zoneinfo.ZoneInfo | None = None
        try:
            detected_tzname = zoneinfo.ZoneInfo(request.COOKIES.get("totem_timezone"))
        except (zoneinfo.ZoneInfoNotFoundError, TypeError):
            pass
        user: "User" = request.user
        if user.is_authenticated and user.timezone:
            tzname = user.timezone
        if detected_tzname is not None and detected_tzname != tzname:
            tzname = detected_tzname
            if user.is_authenticated:
                user.timezone = tzname
                user.save()
        if tzname:
            timezone.activate(tzname)
        else:
            timezone.deactivate()
        return self.get_response(request)


class CDNGuard:
    """Raise a 404 if a request is made from DJANGO_STATIC_HOST for any URL except for the /static/ directory."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.get_host() == settings.STATIC_HOST:
            if not request.build_absolute_uri().startswith(settings.STATIC_URL):
                raise Http404
        return self.get_response(request)
