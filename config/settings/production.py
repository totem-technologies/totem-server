import socket
from urllib.parse import urlsplit

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
ALLOWED_HOSTS.append(SITE_HOST)  # noqa: F405

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
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-referrer-policy
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# CSP (Content Security Policy)
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/6.0/ref/csp/
# Starting in report-only mode to collect violations without breaking the site.
# Once reports are clean, move this to SECURE_CSP to enforce.
#
# Three policies:
# - SECURE_CSP_REPORT_ONLY: the site policy. Inline scripts require nonces
#   ({{ csp_nonce }} in templates); external scripts still go by host list.
# - CSP_PROXIED_SITE_OVERRIDE: marketing pages proxied from Webflow — HTML
#   we don't render, so inline scripts stay allowed there.
# - CSP_ROOM_OVERRIDE: the Flutter room app at /room/ — same inline
#   constraint, plus its wasm/CanvasKit/LiveKit needs, which the rest of
#   the site shouldn't grant.
_DO_CDN = f"*.{env('DO_STORAGE_BUCKET_REGION', default='nyc3')}.cdn.digitaloceanspaces.com"
_PROXIED_SITE = PROXIED_SITE_BASE_URL.rstrip("/")  # noqa: F405
# Flutter room app upstream — served same-origin via the /room/ proxy, but
# its HTML/assets reference absolute URLs on the upstream's public host
# (e.g. a workers.dev URL in staging).
_ROOM_APP = f"https://{ROOM_APP_PROXY_BROWSER_HOST}"  # noqa: F405
# Static CDN origins. STATIC_HOST is this env's active host; cdn.totem.org
# is always included because the Flutter room app hardcodes the production
# CDN for shared assets.
_STATIC_ORIGINS = sorted({f"https://{h}" for h in (STATIC_HOST, "cdn.totem.org") if h})
_REPORT_URI = "https://o1324443.ingest.sentry.io/api/4505270983065600/security/?sentry_key=fc28dfc40b014a8fa120aa1d9c279112"

# LiveKit signaling — the room app opens the WebSocket straight from the
# browser (media flows over WebRTC, which CSP doesn't govern).
_LIVEKIT_ORIGINS: list[str] = []
if LIVEKIT_URL:  # noqa: F405
    _LIVEKIT_HOST = urlsplit(LIVEKIT_URL).netloc  # noqa: F405
    if _LIVEKIT_HOST.endswith(".livekit.cloud"):
        # LiveKit Cloud redirects clients to regional endpoints
        # (e.g. <project>.oashburn1b.production.livekit.cloud), so the
        # project host alone isn't enough.
        _LIVEKIT_ORIGINS = ["wss://*.livekit.cloud", "https://*.livekit.cloud"]
    else:
        _LIVEKIT_ORIGINS = [f"wss://{_LIVEKIT_HOST}", f"https://{_LIVEKIT_HOST}"]

# External script hosts. These stay valid alongside nonces: a nonce gates
# inline scripts only, external <script src> is still matched by host.
_CSP_SCRIPT_HOSTS = [
    "https://js.sentry-cdn.com",
    "https://browser.sentry-cdn.com",
    "https://static.cloudflareinsights.com",  # beacon is edge-injected by Cloudflare
    "https://us-assets.i.posthog.com",
    "https://app.posthog.com",
    "https://e.totem.org",
    _PROXIED_SITE,
] + _STATIC_ORIGINS

# Directives shared by the site policy and the marketing override.
_CSP_BASE = {
    "default-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, _PROXIED_SITE] + _STATIC_ORIGINS,
    "img-src": [CSP.SELF, _DO_CDN, "data:", _PROXIED_SITE] + _STATIC_ORIGINS,
    "font-src": [CSP.SELF, _PROXIED_SITE] + _STATIC_ORIGINS,
    "connect-src": [
        CSP.SELF,
        "https://o1324443.ingest.sentry.io",
        "https://o1324443.ingest.us.sentry.io",
        "https://e.totem.org",
        "https://static.cloudflareinsights.com",
        "https://us.i.posthog.com",
        "https://us-assets.i.posthog.com",
        _DO_CDN,
    ]
    + _STATIC_ORIGINS,
    # youtube-nocookie/npr: video and audio embeds in marketing/blog content.
    "frame-src": ["https://e.totem.org", "https://www.youtube-nocookie.com", "https://www.npr.org"],
    "worker-src": [CSP.SELF, "blob:"],  # blob: workers are spawned by Sentry/PostHog tooling
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "report-uri": [_REPORT_URI],
}

SECURE_CSP_REPORT_ONLY = {
    **_CSP_BASE,
    "script-src": [CSP.SELF, CSP.NONCE] + _CSP_SCRIPT_HOSTS,
}

# Marketing pages: Webflow HTML we can't nonce, so inline stays allowed.
CSP_PROXIED_SITE_OVERRIDE = {
    **_CSP_BASE,
    "script-src": [CSP.SELF, CSP.UNSAFE_INLINE] + _CSP_SCRIPT_HOSTS,
}

# Flutter room app at /room/: its index.html bootstrap script is inline,
# the renderer is a WebAssembly module fetched from gstatic, images render
# via blob: object URLs, and fallback fonts (e.g. emoji) come from Google
# Fonts at runtime.
CSP_ROOM_OVERRIDE = {
    "default-src": [CSP.SELF],
    "script-src": [
        CSP.SELF,
        CSP.UNSAFE_INLINE,
        CSP.WASM_UNSAFE_EVAL,
        "https://www.gstatic.com",
        _ROOM_APP,
    ]
    + _STATIC_ORIGINS,
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, _ROOM_APP] + _STATIC_ORIGINS,
    "img-src": [CSP.SELF, "data:", "blob:", _DO_CDN, _ROOM_APP] + _STATIC_ORIGINS,
    "font-src": [CSP.SELF, "https://fonts.gstatic.com", _ROOM_APP] + _STATIC_ORIGINS,
    "connect-src": [
        CSP.SELF,
        "https://www.gstatic.com",
        "https://fonts.gstatic.com",
        _DO_CDN,
        _ROOM_APP,
    ]
    + _STATIC_ORIGINS
    + _LIVEKIT_ORIGINS,
    "worker-src": [CSP.SELF, "blob:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "report-uri": [_REPORT_URI],
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
