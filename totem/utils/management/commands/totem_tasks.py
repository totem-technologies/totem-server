import traceback
from collections.abc import Callable

import sentry_sdk
from django.conf import settings
from django.core.management.base import BaseCommand
from sentry_sdk.crons.decorator import monitor

from totem.email.tasks import tasks as email_tasks
from totem.notifications.tasks import tasks as notification_tasks
from totem.rooms.tasks import tasks as room_tasks
from totem.spaces.tasks import tasks as space_tasks
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


class TasksFailed(Exception):
    pass


ALL_TASKS: list[list[Callable]] = [space_tasks, email_tasks, notification_tasks, user_tasks, room_tasks]


def run_tasks_impl(tasks: list[list[Callable]] = ALL_TASKS):
    """Run every task, even if an earlier one fails. Failures are reported to
    Sentry individually, then re-raised together so the cron check-in errors."""
    failed: list[str] = []
    for task_list in tasks:
        for task in task_list:
            try:
                task()
            except Exception as e:
                traceback.print_exc()
                sentry_sdk.capture_exception(e)
                failed.append(getattr(task, "__qualname__", repr(task)))
    if failed:
        raise TasksFailed(f"Tasks failed: {', '.join(failed)}")
