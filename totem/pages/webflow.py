import requests
from django.conf import settings

requests_session = requests.Session()


def get_webflow_page(page: str | None) -> str:
    print(f"getting webflow page {page}")
    # proxy webflow pages from remote server
    # Send a GET request to the Webflow page
    base_url = settings.WEBFLOW_BASE_URL
    if page is None:
        content = _get(base_url)
    else:
        content = _get(f"{base_url}{page}")
    return content


def _get(url: str) -> str:
    return requests_session.get(url, timeout=5).content.decode("utf-8")
