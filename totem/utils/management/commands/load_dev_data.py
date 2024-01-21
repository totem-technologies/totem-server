# Django management command that populates the database with the initial data in a development environment.
# Uses models from the app and does not load data from the fixtures folder.

import random

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

fake = Faker(["en-US"]).unique


class Command(BaseCommand):
    help = "Populates the database with the initial data in a development environment."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise RuntimeError("This command should only be run in a development environment.")
        print("Loading fixtures...")
        load_fixtures_impl()


def load_fixtures_impl():
    # Create superuser and users
    from totem.users.models import KeeperProfile, User

    # Create superuser if it doesn't exist
    if not User.objects.filter(email="admin@admin.com").exists():
        User.objects.create_superuser(name="admin", email="admin@admin.com", password=fake.password())

    # Create staff
    staff = []
    for i in range(5):
        u = User.objects.create_user(
            name=fake.name(),
            email=fake.email(),
            password=fake.password(),
            is_staff=True,
        )
        KeeperProfile.objects.create(user=u, bio=fake.paragraph(nb_sentences=20))
        staff.append(u)

    # Create users
    users = []
    for i in range(15):
        users.append(
            User.objects.create_user(
                name=fake.name(),
                email=fake.email(),
                password=fake.password(),
            )
        )

    # Create circles
    from totem.circles.models import Circle

    circles = []
    for i in range(15):
        circles.append(
            Circle.objects.create(
                published=True,
                title=fake.bs().title(),
                subtitle=fake.sentence(),
                author=staff[i % len(staff)],
                content=fake.paragraph(nb_sentences=20),
                recurring="Every week",
            )
        )

    # Create circle events
    from totem.circles.models import CircleEvent

    for circle in circles:
        for i in range(15):
            e = CircleEvent.objects.create(
                circle=circle,
                start=fake.date_time_between(start_date="+1d", end_date="+1y", tzinfo=timezone.utc),
                meeting_url=fake.url(),
            )
            e.attendees.add(circle.author)
            e.attendees.add(*random.sample(users, 4))
