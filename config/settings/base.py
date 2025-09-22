"""
Base settings to build other settings files upon.
"""

import base64
import json
from pathlib import Path

import django
import environ

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# totem/
APPS_DIR = BASE_DIR / "totem"
env = environ.Env()
TEST = False


def b64_json_env(key: str):
    empty_json = "e30K"
    return json.loads(base64.b64decode(env(key, default=empty_json)))  # type: ignore


READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)  # type: ignore
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)  # type: ignore
SITE_HOST = env("SITE_HOST", default="localhost:8000")  # type: ignore
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "UTC"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
DATETIME_FORMAT = "jS M Y fA e"

# https://docs.djangoproject.com/en/dev/ref/settings/#site-id

# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]
FORMAT_MODULE_PATH = ["totem.formats"]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
# DATABASES["default"]["ATOMIC_REQUESTS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.humanize",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "allauth.account",
    "allauth.socialaccount",
    "allauth",
    "auditlog",
    "corsheaders",
    "imagekit",
    "impersonate",
    "ninja",
    "taggit",
]

LOCAL_APPS = [
    "totem.api",
    "totem.blog",
    "totem.circles",
    "totem.course",
    "totem.dev",
    "totem.email",
    "totem.onboard",
    "totem.pages",
    "totem.plans",
    "totem.repos",
    "totem.uploads",
    "totem.users",
    "totem.utils",
    "totem.notifications",
]

# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "totem.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "users:redirect"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "users:signup"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "impersonate.middleware.ImpersonateMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "totem.utils.middleware.robotnoindex",
    "totem.utils.middleware.TimezoneMiddleware",
    "totem.utils.middleware.CDNGuard",
    "auditlog.middleware.AuditlogMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]
STATIC_HOST = env.str("DJANGO_STATIC_HOST", default=None)  # type: ignore
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
if STATIC_HOST:
    STATIC_URL = f"https://{STATIC_HOST}/static/"

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

USE_S3_STORAGE = env.bool("USE_S3_STORAGE", default=False)  # type: ignore
if USE_S3_STORAGE:
    _region = env("DO_STORAGE_BUCKET_REGION", default="nyc3")  # type: ignore
    STORAGES["default"] = {  # type: ignore
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": env("DO_STORAGE_BUCKET_KEY"),
            "secret_key": env("DO_STORAGE_BUCKET_SECRET"),
            "bucket_name": env("DO_STORAGE_BUCKET_NAME"),
            "region_name": _region,
            "endpoint_url": f"https://{_region}.digitaloceanspaces.com",
            "default_acl": "public-read",
            "querystring_auth": False,
            "custom_domain": f"{env('DO_STORAGE_BUCKET_NAME')}.{_region}.cdn.digitaloceanspaces.com",
        },
    }


# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates

# https://nickjanetakis.com/blog/django-4-1-html-templates-are-cached-by-default-with-debug-true
default_loaders = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
cached_loaders = [("django.template.loaders.cached.Loader", default_loaders)]

TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates"), django.__path__[0] + "/forms/templates"],  # type: ignore
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "totem.users.context_processors.allauth_settings",
            ],
            "loaders": default_loaders if DEBUG else cached_loaders,
        },
    }
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-age
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 52  # 1 year
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",  # type: ignore
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5
EMAIL_BASE_URL = env("EMAIL_BASE_URL", default=f"https://{SITE_HOST}")  # type: ignore
SITE_BASE_URL = EMAIL_BASE_URL

# https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = env(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="Totem <computer@totem.org>",  # type: ignore
)
# https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)  # type: ignore
# https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = env(
    "DJANGO_EMAIL_SUBJECT_PREFIX",
    default="[Totem]",  # type: ignore
)
EMAIL_SUPPORT_ADDRESS = "help@totem.org"
EMAIL_SHOW_ENV_BANNER = env.bool("EMAIL_SHOW_ENV_BANNER", default=False)  # type: ignore
MAILERLITE_API_KEY = env("MAILERLITE_API_KEY", default="")  # type: ignore
MAILERSEND_API_TOKEN = env("MAILERSEND_API_TOKEN", default="")  # type: ignore
MAILERSEND_COLLECT_ACTIVITY = env.bool("MAILERSEND_COLLECT_ACTIVITY", default=False)  # type: ignore
MAILERSEND_DOMAIN_ID = env("MAILERSEND_DOMAIN_ID", default="")  # type: ignore
BREVO_API_KEY = env("BREVO_API_KEY", default="")  # type: ignore
SEND_BREVO_EMAILS = env.bool("SEND_BREVO_EMAILS", default=False)  # type: ignore

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("""Bo""", "bo@totem.org")]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}


# django-allauth
# ------------------------------------------------------------------------------
ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", True)  # type: ignore
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_LOGIN_METHODS = {"email"}
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_ADAPTER = "totem.users.adapters.AccountAdapter"
# https://django-allauth.readthedocs.io/en/latest/forms.html
ACCOUNT_FORMS = {"signup": "totem.users.forms.UserSignupForm"}
# https://django-allauth.readthedocs.io/en/latest/configuration.html
SOCIALACCOUNT_ADAPTER = "totem.users.adapters.SocialAccountAdapter"
# https://django-allauth.readthedocs.io/en/latest/forms.html
SOCIALACCOUNT_FORMS = {"signup": "totem.users.forms.UserSocialSignupForm"}


# Your stuff...
# ------------------------------------------------------------------------------

# Firebase Cloud Messaging
# ------------------------------------------------------------------------------

FIREBASE_FCM_CREDENTIALS_JSON_B64 = b64_json_env("FIREBASE_FCM_CREDENTIALS_JSON_B64")

# Custom
# ------------------------------------------------------------------------------
TOTEM_RUN_TASKS_TOKEN = env("TOTEM_RUN_TASKS_TOKEN")
TOTEM_ASYNC_WORKER_QUEUE_ENABLED = env.bool("TOTEM_ASYNC_WORKER_QUEUE_ENABLED", default=True)  # type: ignore


ROBOTS_NO_INDEX = env.bool("ROBOT_NO_INDEX", False)  # type: ignore

# admin banner
# ------------------------------------------------------------------------------
ENVIRONMENT_NAME = env("ENVIRONMENT_NAME", default="Development")  # type: ignore
ENVIRONMENT_COLOR = env("ENVIRONMENT_COLOR", default="gray")  # type: ignore

# django-taggit
# ------------------------------------------------------------------------------
TAGGIT_CASE_INSENSITIVE = True
TAGGIT_TAGS_FROM_STRING = "totem.utils.tag_utils.parse_tags"


# sentry
# ------------------------------------------------------------------------------
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="development")  # type: ignore
if not DEBUG:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn="https://fc28dfc40b014a8fa120aa1d9c279112@o1324443.ingest.sentry.io/4505270983065600",
        integrations=[
            DjangoIntegration(),
        ],
        environment=SENTRY_ENVIRONMENT,  # type: ignore
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=True,
        profile_lifecycle="trace",
        enable_logs=True,
    )

# posthog
# ------------------------------------------------------------------------------
POSTHOG_API_KEY = env("POSTHOG_API_KEY", default="phc_OJCztWvtlN5scoDe58jLipnOTCBugeidvZlni3FIy9z")  # type: ignore


# google API
# ------------------------------------------------------------------------------
GOOGLE_SERVICE_JSON = b64_json_env("GOOGLE_SERVICE_JSON_B64")
GOOGLE_CALENDAR_ID = env(
    "GOOGLE_CALENDAR_ID",
    default="c_ddf4458b375a1d28389aee93ed234ac1b51ee98ed37d09a8a22509a950bac115@group.calendar.google.com",  # type: ignore
)
SAVE_TO_GOOGLE_CALENDAR = env.bool("SAVE_TO_GOOGLE_CALENDAR", default=False)  # type: ignore


# Slack
# ------------------------------------------------------------------------------
SLACK_BOT_TOKEN = env("SLACK_BOT_TOKEN", default=None)  # type: ignore
SLACK_CHANNEL_ID = env("SLACK_CHANNEL_ID", default=None)  # type: ignore


# Impersonate
# ------------------------------------------------------------------------------
IMPERSONATE = {
    "REQUIRE_SUPERUSER": True,
}


# CORS
# ------------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    "https://app.posthog.com",
    "https://us.i.posthog.com",
    "https://js.sentry-cdn.com",
    "https://totem-technologies.github.io",
]
if STATIC_HOST:
    CORS_ALLOWED_ORIGINS.append(f"https://{STATIC_HOST}")


# Auditlog
# ------------------------------------------------------------------------------
AUDITLOG_INCLUDE_ALL_MODELS = True
AUDITLOG_DISABLE_ON_RAW_SAVE = True
AUDITLOG_EXCLUDE_TRACKING_MODELS = ["totem.email.models.EmailLog"]


# Webflow
# ------------------------------------------------------------------------------
WEBFLOW_BASE_URL = env("WEBFLOW_BASE_URL", default="https://wf.totem.org/")  # type: ignore


# Social
# ------------------------------------------------------------------------------
SOCIAL_LINKS = {
    "bluesky": "https://bsky.app/profile/totem.org",
    "instagram": "https://www.instagram.com/totemorg/",
    "github": "https://github.com/totem-technologies/",
    "linkedin": "https://www.linkedin.com/company/totemorg/",
}


# LiveKit
# ------------------------------------------------------------------------------
LIVEKIT_API_KEY = env("LIVEKIT_API_KEY", default=None)
LIVEKIT_API_SECRET = env("LIVEKIT_API_SECRET", default=None)