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

    # Create Space Categories
    from totem.circles.models import SpaceCategory

    categories = []
    for i in range(5):
        categories.append(
            SpaceCategory.objects.create(
                name=fake.word(),
                slug=fake.slug(),
                description=fake.paragraph(nb_sentences=20),
            )
        )

    # Create spaces
    from totem.circles.models import Space

    spaces = []
    for i in range(15):
        space = Space.objects.create(
            published=True,
            title=fake.bs().title(),
            subtitle=fake.sentence(),
            author=staff[i % len(staff)],
            content=fake.paragraph(nb_sentences=20),
            recurring="Every week",
        )
        space.categories.add(*random.sample(categories, 2))
        space.subscribed.add(space.author, *random.sample(users, 4))
        spaces.append(space)

    # Create sessions
    from totem.circles.models import Session

    for space in spaces:
        for i in range(15):
            session = Session.objects.create(
                space=space,
                start=timezone.make_aware(fake.date_time_between(start_date="+1d", end_date="+1y")),
                meeting_url=fake.url(),
            )
            session.attendees.add(space.author)
            session.attendees.add(*random.sample(users, 4))
