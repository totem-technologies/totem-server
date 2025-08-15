"""
With these settings, tests run faster.
"""

from .base import *  # noqa
from .base import env

del STORAGES  # noqa: F821

TEST = True
# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="3ZbhRn2rCcQFYICMwXg2o34S6Rsl9IMchyIc5v2OTFILqiTeDZU3MVvsaV1nQfoQ",  # type: ignore
)
# https://docs.djangoproject.com/en/dev/ref/settings/#test-runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SITE_BASE_URL = "http://testserver"

# DEBUGGING FOR TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore # noqa: F405

TOTEM_ASYNC_WORKER_QUEUE_ENABLED = False

# Make sure we don't talk to any real APIs
# ------------------------------------------------------------------------------
POSTHOG_API_KEY = "test"
SAVE_TO_GOOGLE_CALENDAR = False
MAILERLITE_API_KEY = None
SLACK_BOT_TOKEN = None
SLACK_CHANNEL_ID = "fpksdfksdf"
FIREBASE_FCM_CREDENTIALS_JSON_B64 = None
