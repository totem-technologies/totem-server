from collections.abc import Callable

from django.conf import settings
from django.core.management.base import BaseCommand
from sentry_sdk.crons.decorator import monitor

from totem.circles.tasks import tasks as space_tasks
from totem.email.tasks import tasks as email_tasks
from totem.notifications.tasks import tasks as notification_tasks
from totem.users.tasks import tasks as user_tasks


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


def run_tasks_impl():
    tasks: list[list[Callable]] = [space_tasks, email_tasks, notification_tasks, user_tasks]
    for task_list in tasks:
        for task in task_list:
            task()
