"""Select a room build for two hours without changing the login session's expiry."""

import re
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import escape_leading_slashes

PREVIEW_KEY = "room_preview"
PREVIEW_TTL = timedelta(hours=2)
WORKER_NAME = "totem-web-preview"
_ALIAS = re.compile(r"pr-[1-9][0-9]*-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")


def valid_preview_alias(alias):
    return isinstance(alias, str) and len(f"{alias}-{WORKER_NAME}") <= 63 and _ALIAS.fullmatch(alias) is not None


def preview_hostname(alias):
    return f"{alias}-{WORKER_NAME}.lopkerk.workers.dev"


def selected_alias(session):
    if not settings.ROOM_PREVIEW_ENABLED:
        return None
    selection = session.get(PREVIEW_KEY)
    if isinstance(selection, dict):
        alias = selection.get("alias")
        expires_at = selection.get("expires_at")
        if (
            valid_preview_alias(alias)
            and isinstance(expires_at, (int, float))
            and expires_at > timezone.now().timestamp()
        ):
            return alias
    session.pop(PREVIEW_KEY, None)
    return None


class RoomPreviewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.ROOM_PREVIEW_ENABLED:
            return self.get_response(request)

        if request.method == "GET" and PREVIEW_KEY in request.GET:
            choices = request.GET.getlist(PREVIEW_KEY)
            if len(choices) != 1 or (choices[0] != "off" and not valid_preview_alias(choices[0])):
                response = HttpResponseBadRequest("Invalid room preview alias.")
            else:
                alias = choices[0]
                if alias == "off":
                    request.session.pop(PREVIEW_KEY, None)
                else:
                    request.session[PREVIEW_KEY] = {
                        "alias": alias,
                        "expires_at": (timezone.now() + PREVIEW_TTL).timestamp(),
                    }
                query = request.GET.copy()
                del query[PREVIEW_KEY]
                path = escape_leading_slashes(request.path)
                response = HttpResponseRedirect(f"{path}?{query.urlencode()}" if query else path)
            add_never_cache_headers(response)
            return response

        selected_alias(request.session)
        return self.get_response(request)
