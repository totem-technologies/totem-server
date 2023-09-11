from django.core.management.base import BaseCommand

from totem.api.api import run_tasks_impl


class Command(BaseCommand):
    help = "Run tasks for Totem."

    def handle(self, *args, **options):
        print("Running tasks...")
        run_tasks_impl()
        print("Done.")
