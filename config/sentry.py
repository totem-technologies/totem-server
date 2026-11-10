import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration


def init_sentry(dsn: str, environment: str) -> bool:
    """Initialize Sentry, or leave it disabled when no DSN is configured.

    The DSN is a secret supplied through the environment. Without one, the SDK
    is never initialized, so every sentry_sdk call in the app (capture_exception,
    cron monitors, etc.) is a no-op. Returns whether Sentry was enabled.
    """
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            DjangoIntegration(),
        ],
        environment=environment,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=True,
        profile_lifecycle="trace",
        enable_logs=True,
    )
    return True
