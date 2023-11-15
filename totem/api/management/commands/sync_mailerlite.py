from django.conf import settings
from django.core.management.base import BaseCommand
from sentry_sdk.crons.decorator import monitor

from totem.users.models import User
from totem.utils.mailerlite import upload_users_to_mailerlite_batch


class Command(BaseCommand):
    help = "Syncs Mailerlite subscribers with Totem users."

    def handle(self, *args, **options):
        if settings.DEBUG:
            self._doit()
        else:
            with monitor(monitor_slug="sync_mailerlite"):
                self._doit()

    def _doit(self):
        test = settings.SENTRY_ENVIRONMENT != "production"
        if test:
            print("Running in test mode.")
        print("Syncing Mailerlite subscribers...")
        users = list(User.objects.all())
        upload_users_to_mailerlite_batch(users, test=test)
        print("Done.")
