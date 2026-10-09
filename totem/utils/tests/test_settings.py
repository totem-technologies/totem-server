import os
import subprocess
import sys

import pytest

# Settings modules configure Sentry at import time, so each one is loaded in a
# fresh interpreter to observe the real effect.
SENTRY_ACTIVE_SCRIPT = """
import importlib, sys
import sentry_sdk
importlib.import_module(sys.argv[1])
print(sentry_sdk.get_client().is_active())
"""


def sentry_active_after_import(settings_module: str, extra_env: dict[str, str] | None = None) -> bool:
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_DEBUG"}
    env.update(extra_env or {})
    result = subprocess.run(
        [sys.executable, "-c", SENTRY_ACTIVE_SCRIPT, settings_module],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip().splitlines()[-1] == "True"


@pytest.mark.parametrize("settings_module", ["config.settings.local", "config.settings.test"])
def test_sentry_disabled_outside_production_without_django_debug(settings_module: str):
    assert not sentry_active_after_import(settings_module)


def test_sentry_enabled_in_production():
    assert sentry_active_after_import(
        "config.settings.production",
        {"DJANGO_SECRET_KEY": "test", "DJANGO_ADMIN_URL": "admin/"},
    )
