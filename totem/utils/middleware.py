import zoneinfo

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone


def robotnoindex(get_response):
    def middleware(request: HttpRequest):
        response = get_response(request)

        if settings.ROBOTS_NO_INDEX:
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet, notranslate, noimageindex"

        return response

    return middleware


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        detected_tzname = request.COOKIES.get("totem_timezone")
        tzname = request.session.get("totem_timezone")
        if tzname is None and detected_tzname is not None:
            tzname = detected_tzname
        if tzname:
            timezone.activate(zoneinfo.ZoneInfo(tzname))
        else:
            timezone.deactivate()
        return self.get_response(request)
