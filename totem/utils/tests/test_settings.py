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


PRODUCTION_ENV = {
    "DJANGO_SECRET_KEY": "test",
    "DJANGO_ADMIN_URL": "admin/",
    "SENTRY_DSN": "https://public@o0.ingest.sentry.io/0",
}


def import_settings(settings_module: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("DJANGO_DEBUG", "SENTRY_DSN")}
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-c", SENTRY_ACTIVE_SCRIPT, settings_module],
        env=env,
        capture_output=True,
        text=True,
    )


def sentry_active_after_import(settings_module: str, extra_env: dict[str, str] | None = None) -> bool:
    result = import_settings(settings_module, extra_env)
    result.check_returncode()
    return result.stdout.strip().splitlines()[-1] == "True"


@pytest.mark.parametrize("settings_module", ["config.settings.local", "config.settings.test"])
def test_sentry_disabled_outside_production_without_django_debug(settings_module: str):
    assert not sentry_active_after_import(settings_module)


def test_sentry_enabled_in_production():
    assert sentry_active_after_import("config.settings.production", PRODUCTION_ENV)


@pytest.mark.parametrize("dsn", [None, ""])
def test_sentry_disabled_in_production_without_dsn(dsn: str | None):
    env = {k: v for k, v in PRODUCTION_ENV.items() if k != "SENTRY_DSN"}
    if dsn is not None:
        env["SENTRY_DSN"] = dsn
    assert not sentry_active_after_import("config.settings.production", env)
