from urllib.parse import urljoin

from django.conf import settings
from django.http import HttpRequest


def full_url(path: str) -> str:
    return urljoin(settings.SITE_BASE_URL, path)


def is_ajax(request: HttpRequest) -> bool:
    return request.META.get("HTTP_ACCEPT") == "application/json"
