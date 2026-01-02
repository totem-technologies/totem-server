import re

from django.utils.regex_helper import _lazy_re_compile
from django.views.debug import SafeExceptionReporterFilter


class HardenedReporterFilter(SafeExceptionReporterFilter):
    """
    Extends the default scrubbing regex to include B64, ID, and URL patterns.
    """

    hidden_settings = _lazy_re_compile(
        "API|AUTH|TOKEN|KEY|SECRET|PASS|SIGNATURE|HTTP_COOKIE|B64|DATABASE_URL|WEBHOOK", flags=re.I
    )
