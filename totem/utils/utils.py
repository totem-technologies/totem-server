from urllib.parse import urljoin

from django.conf import settings
from django.http import HttpRequest


def full_url(path: str) -> str:
    return urljoin(settings.SITE_BASE_URL, path)


def is_ajax(request: HttpRequest) -> bool:
    return request.META.get("HTTP_ACCEPT") == "application/json"


def request_log_context(request: HttpRequest, email: str) -> dict[str, str]:
    """Standard `extra` fields for auth-flow log lines, shared by the web and API login views."""
    return {
        "email": email,
        "ip_address": request.META.get("REMOTE_ADDR", ""),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }
