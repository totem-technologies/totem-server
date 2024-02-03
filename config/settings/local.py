from .base import *  # noqa
from .base import env


SITE_HOST: str = SITE_HOST  # noqa: F405

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="ug27gQVlBLKLnF2a09adWFdgWWZPG6s8PZWnCdjzDjJoNrUnr0oSosLwjwZudNSt",  # type: ignore
)
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
# 10.0.2.2 for android emulator
ALLOWED_HOSTS = ["localhost", "0.0.0.0", "127.0.0.1", "10.0.2.2", SITE_HOST]
CSRF_TRUSTED_ORIGINS = [f"https://{SITE_HOST}", f"http://{SITE_HOST}"]

# CACHES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#caches
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.dummy.DummyCache",
#     }
# }

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
USE_MAILPIT = env.bool("USE_MAILPIT", default=False)  # type: ignore
EMAIL_BASE_URL = env("EMAIL_BASE_URL", default=f"http://{SITE_HOST}")  # noqa: F405 # type: ignore
if USE_MAILPIT:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "mailpit"
    EMAIL_PORT = 1025
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # type: ignore

# INSTALLED_APPS += ["anymail"]  # noqa: F405
# EMAIL_BACKEND = "anymail.backends.mailersend.EmailBackend"
# ANYMAIL = {"MAILERSEND_API_TOKEN": env("MAILERSEND_API_TOKEN"), "MAILERSEND_BATCH_SEND_MODE": "use-bulk-email"}

# WhiteNoise
# ------------------------------------------------------------------------------
# http://whitenoise.evans.io/en/latest/django.html#using-whitenoise-in-development
INSTALLED_APPS = ["whitenoise.runserver_nostatic"] + INSTALLED_APPS  # noqa: F405


# django-debug-toolbar
# ------------------------------------------------------------------------------
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": ["debug_toolbar.panels.redirects.RedirectsPanel"],
    "SHOW_TEMPLATE_CONTEXT": True,
}

# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#internal-ips
INTERNAL_IPS = type("c", (), {"__contains__": lambda *a: True})()

# django-extensions
# ------------------------------------------------------------------------------
# https://django-extensions.readthedocs.io/en/latest/installation_instructions.html#configuration
INSTALLED_APPS += ["django_extensions"]  # noqa: F405


# # Email Tester (Uncomment)
# # # Anymail
# # # ------------------------------------------------------------------------------
# # # https://anymail.readthedocs.io/en/stable/installation/#installing-anymail
# INSTALLED_APPS += ["anymail"]  # noqa: F405
# # # https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
# # # https://anymail.readthedocs.io/en/stable/installation/#anymail-settings-reference
# # # https://anymail.readthedocs.io/en/stable/esps/mailgun/
# EMAIL_BACKEND = "anymail.backends.mailersend.EmailBackend"
# ANYMAIL = {
#     "MAILERSEND_API_TOKEN": env("MAILERSEND_API_TOKEN"),
#     "MAILERSEND_BATCH_SEND_MODE": "use-bulk-email",
# }
# DEFAULT_FROM_EMAIL = env(
#     "DJANGO_DEFAULT_FROM_EMAIL",
#     default="Totem <noreply@totem.org>",
# )
# # https://docs.djangoproject.com/en/dev/ref/settings/#server-email
# SERVER_EMAIL = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
# # https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
# EMAIL_SUBJECT_PREFIX = env(
#     "DJANGO_EMAIL_SUBJECT_PREFIX",
#     default="[Totem]",
# )
