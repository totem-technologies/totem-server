from urllib.parse import urljoin

from django.conf import settings


def full_url(path: str) -> str:
    return urljoin(settings.EMAIL_BASE_URL, path)
