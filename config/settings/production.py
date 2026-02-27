import socket

from django.utils.csp import CSP

from .base import *  # noqa
from .base import MAILERSEND_API_TOKEN, env

STATIC_HOST = STATIC_HOST or None  # noqa: F405

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env("DJANGO_SECRET_KEY")
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=["totem.org", "totem.kbl.io"])
ALLOWED_HOSTS.append(str(socket.getaddrinfo(socket.gethostname(), "http")[0][4][0]))
if STATIC_HOST:
    ALLOWED_HOSTS.append(STATIC_HOST)
ALLOWED_HOSTS += SITE_HOST  # noqa: F405

# DATABASES
# ------------------------------------------------------------------------------
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)  # noqa: F405

# CACHES
# ------------------------------------------------------------------------------
# CACHES = {
#     "default": {
#         "BACKEND": "django_redis.cache.RedisCache",
#         "LOCATION": env("REDIS_URL"),
#         "OPTIONS": {
#             "CLIENT_CLASS": "django_redis.client.DefaultClient",
#             # Mimicking memcache behavior.
#             # https://github.com/jazzband/django-redis#memcached-exceptions-behavior
#             "IGNORE_EXCEPTIONS": True,
#         },
#     }
# }

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
CSRF_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/topics/security/#ssl-https
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
SECURE_HSTS_SECONDS = 518400
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = env.bool("DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", default=True)

# CSP (Content Security Policy)
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/6.0/ref/csp/
# Starting in report-only mode to collect violations without breaking the site.
# Once reports are clean, move this to SECURE_CSP to enforce.
_DO_CDN = f"*.{env('DO_STORAGE_BUCKET_REGION', default='nyc3')}.cdn.digitaloceanspaces.com"
_CSP_SCRIPT_SRC = [
    CSP.SELF,
    CSP.UNSAFE_INLINE,
    "https://js.sentry-cdn.com",
    "https://www.googletagmanager.com",
    "https://googleads.g.doubleclick.net",
    "https://static.cloudflareinsights.com",
    "https://e.totem.org",
]
_CSP_STYLE_SRC = [
    CSP.SELF,
    CSP.UNSAFE_INLINE,
]
_CSP_IMG_SRC = [
    CSP.SELF,
    _DO_CDN,
    "data:",
    "https://googleads.g.doubleclick.net",
    "https://www.googleadservices.com",
    "https://www.google.com",
]
_CSP_CONNECT_SRC = [
    CSP.SELF,
    "https://o1324443.ingest.sentry.io",
    "https://e.totem.org",
    "https://www.google-analytics.com",
    "https://www.googletagmanager.com",
    "https://analytics.google.com",
    "https://static.cloudflareinsights.com",
    _DO_CDN,
]
if STATIC_HOST:
    _CSP_SCRIPT_SRC.append(f"https://{STATIC_HOST}")
    _CSP_STYLE_SRC.append(f"https://{STATIC_HOST}")
    _CSP_IMG_SRC.append(f"https://{STATIC_HOST}")
    _CSP_CONNECT_SRC.append(f"https://{STATIC_HOST}")

SECURE_CSP_REPORT_ONLY = {
    "default-src": [CSP.SELF],
    "script-src": _CSP_SCRIPT_SRC,
    "style-src": _CSP_STYLE_SRC,
    "img-src": _CSP_IMG_SRC,
    "font-src": [CSP.SELF] + ([f"https://{STATIC_HOST}"] if STATIC_HOST else []),
    "connect-src": _CSP_CONNECT_SRC,
    "frame-src": ["https://e.totem.org", "https://www.googletagmanager.com"],
    "worker-src": [CSP.SELF, "blob:"],  # blob: needed for GTM web workers
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "report-uri": [
        "https://o1324443.ingest.sentry.io/api/4505270983065600/security/?sentry_key=fc28dfc40b014a8fa120aa1d9c279112"
    ],
}

# MEDIA
# ------------------------------------------------------------------------------

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL regex.
ADMIN_URL = env("DJANGO_ADMIN_URL")

# # Anymail
# # ------------------------------------------------------------------------------
# # https://anymail.readthedocs.io/en/stable/installation/#installing-anymail
INSTALLED_APPS += ["anymail"]  # noqa: F405
# # https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
# # https://anymail.readthedocs.io/en/stable/installation/#anymail-settings-reference
# # https://anymail.readthedocs.io/en/stable/esps/mailgun/
EMAIL_BACKEND = "anymail.backends.mailersend.EmailBackend"
ANYMAIL = {"MAILERSEND_API_TOKEN": MAILERSEND_API_TOKEN, "MAILERSEND_BATCH_SEND_MODE": "use-bulk-email"}


# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.security.DisallowedHost": {
            "level": "ERROR",
            "handlers": ["console", "mail_admins"],
            "propagate": True,
        },
    },
}


# Your stuff...
# ------------------------------------------------------------------------------
