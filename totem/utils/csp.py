"""Per-view CSP override that follows the site's configured mode.

Django's stock csp_override / csp_report_only_override decorators capture a
policy dict at import time and target one header. Our proxied views
(marketing site, Flutter room app) serve third-party HTML that can't carry
our nonces, so they need a different policy — but that policy is
environment-specific (settings) and must land on whichever header the site
currently uses (report-only today, enforce later) without touching the
views again.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.http import HttpResponseBase


def csp_override_from_settings[**P](
    setting_name: str,
) -> Callable[[Callable[P, HttpResponseBase]], Callable[P, HttpResponseBase]]:
    """Replace the CSP policy for a view with the one in the named setting.

    The setting is read per-request, so it works with override_settings and
    picks up the deployed environment's values. An empty/missing setting is
    a no-op, and the override only applies to the header(s) the site has
    configured — it never forces a CSP header onto an unconfigured mode.
    """

    def decorator(view_func: Callable[P, HttpResponseBase]) -> Callable[P, HttpResponseBase]:
        @wraps(view_func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> HttpResponseBase:
            response = view_func(*args, **kwargs)
            config = getattr(settings, setting_name, None)
            if config:
                if settings.SECURE_CSP:
                    response._csp_config = config  # type: ignore[attr-defined]
                if settings.SECURE_CSP_REPORT_ONLY:
                    response._csp_ro_config = config  # type: ignore[attr-defined]
            return response

        return wrapped

    return decorator
