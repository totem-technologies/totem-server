from django.core.management.base import BaseCommand, CommandError

from totem.circles.models import CircleEvent
from totem.email import emails
from totem.users.models import User

event_maps = {
    "signup": emails.notify_circle_signup,
    "start": emails.notify_circle_starting,
    "tomorrow": emails.notify_circle_tomorrow,
    "ad": emails.notify_circle_advertisement,
    "missed": emails.missed_event_email,
}


class Command(BaseCommand):
    help = "Send an email of a type to the admin user for testing. Also takes an event slug. Types are: " + ", ".join(
        event_maps.keys()
    )

    def add_arguments(self, parser):
        parser.add_argument("email_type", type=str)
        parser.add_argument("event_slug", type=str, nargs="?", default="bnc867nam")

    def handle(self, *args, **options):
        email_type = options["email_type"]
        event_slug = options["event_slug"]

        user = User.objects.get(email="bo@totem.org")
        event = CircleEvent.objects.get(slug=event_slug)

        try:
            event_maps[email_type](event, user).send()
            print(f"Sent {email_type} email to {user.email}")
        except KeyError:
            raise CommandError(f"Unknown email type: {email_type}")
