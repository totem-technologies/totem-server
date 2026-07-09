from totem.users import analytics


def test_posthog_client_is_inert_outside_production():
    """The dev/test PostHog client must be disabled and must not spawn
    consumer threads: their atexit join blocks every process exit (manage.py
    commands, test runs) for ~5 seconds."""
    assert analytics._posthog.disabled
    assert not analytics._posthog.consumers
