from django.conf import settings
from django.core.management.base import BaseCommand
from sentry_sdk.crons import monitor

from totem.api.api import run_tasks_impl


class Command(BaseCommand):
    help = "Run tasks for Totem."

    def handle(self, *args, **options):
        if settings.DEBUG:
            self._doit()
        else:
            with monitor(monitor_slug="totem_tasks"):
                self._doit()

    def _doit(self):
        print("Running tasks...")
        run_tasks_impl()
        print("Done.")
