import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
requests_session = requests.Session()


class WebflowUnavailable(Exception):
    """Raised when Webflow cannot be reached."""

    pass


def get_webflow_page(page: str | None) -> str:
    """Fetch a page from Webflow. Raises WebflowUnavailable on timeout."""
    base_url = settings.WEBFLOW_BASE_URL
    url = base_url if page is None else f"{base_url}{page}"

    try:
        response = requests_session.get(url, timeout=10)
        response.raise_for_status()
        return response.content.decode("utf-8")
    except requests.exceptions.Timeout:
        logger.warning("Webflow timeout fetching: %s", url)
        raise WebflowUnavailable("Webflow request timed out")
    except requests.exceptions.RequestException as e:
        logger.warning("Webflow error fetching %s: %s", url, e)
        raise WebflowUnavailable(f"Webflow request failed: {e}")
