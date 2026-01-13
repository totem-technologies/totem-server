from django.core.management.base import BaseCommand, CommandError

from totem.circles.models import Session
from totem.email import emails
from totem.users.models import User

session_maps = {
    "signup": emails.notify_session_signup,
    "start": emails.notify_session_starting,
    "tomorrow": emails.notify_session_tomorrow,
    "ad": emails.notify_session_advertisement,
    "missed": emails.missed_session_email,
}


class Command(BaseCommand):
    help = "Send an email of a type to the admin user for testing. Also takes a session slug. Types are: " + ", ".join(
        session_maps.keys()
    )

    def add_arguments(self, parser):
        parser.add_argument("email_type", type=str)
        parser.add_argument("event_slug", type=str, nargs="?", default="bnc867nam")

    def handle(self, *args, **options):
        email_type = options["email_type"]
        event_slug = options["event_slug"]

        user = User.objects.get(email="bo@totem.org")
        session = Session.objects.get(slug=event_slug)

        try:
            session_maps[email_type](session, user).send()
            print(f"Sent {email_type} email to {user.email}")
        except KeyError:
            raise CommandError(f"Unknown email type: {email_type}")
