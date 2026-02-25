import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
requests_session = requests.Session()


class ProxiedSiteUnavailable(Exception):
    """Raised when the proxied site host cannot be reached."""

    pass


def get_proxied_site_page(page: str | None) -> str:
    """Fetch a page from the proxied site host. Raises ProxiedSiteUnavailable on timeout."""
    base_url = settings.PROXIED_SITE_BASE_URL
    url = base_url if page is None else f"{base_url}{page}"

    try:
        response = requests_session.get(url, timeout=10)
        response.raise_for_status()
        return response.content.decode("utf-8")
    except requests.exceptions.Timeout:
        logger.warning("Proxied site timeout fetching: %s", url)
        raise ProxiedSiteUnavailable("Proxied site request timed out")
    except requests.exceptions.RequestException as e:
        logger.warning("Proxied site error fetching %s: %s", url, e)
        raise ProxiedSiteUnavailable(f"Proxied site request failed: {e}")
