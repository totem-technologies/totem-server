"""Populate a freshly migrated development database with representative data."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from totem.blog.models import BlogPost
from totem.course.models import CoursePage
from totem.email.models import SubscribedModel
from totem.notifications.models import FCMDevice
from totem.onboard.models import OnboardModel, ReferralChoices
from totem.pages.models import Redirect
from totem.plans.models import CirclePlan
from totem.repos.models import Prompt
from totem.rooms.models import Room, RoomEventLog
from totem.rooms.schemas import EndReason, RoomStatus, TurnState
from totem.spaces.models import Session, SessionFeedback, SessionFeedbackOptions, Space, SpaceCategory
from totem.users.models import Feedback, KeeperProfile, User

FIXTURE_SEED = 20260803
KEEPER_COUNT = 5
PARTICIPANT_COUNT = 30
SESSION_DAY_OFFSETS = (-730, -540, -365, -270, -180, -120, -90, -60, -30, -14, -7, 7, 30, 90)

CATEGORY_DATA = (
    ("Connection", "connection"),
    ("Grief and Loss", "grief-and-loss"),
    ("Caregiving", "caregiving"),
    ("Identity", "identity"),
    ("Mindfulness", "mindfulness"),
)

SPACE_TITLES = (
    "Community Connections",
    "Living With Loss",
    "Caregiver Check-In",
    "Finding Belonging",
    "Mindful Mondays",
    "Life Transitions",
    "Creative Reflection",
    "Building Resilience",
    "Open Community Circle",
    "Keeper Practice Circle",
)

TIMEZONES = (
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "America/Toronto",
    "Europe/London",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Pacific/Auckland",
)


class Command(BaseCommand):
    help = "Populates a freshly migrated database with representative development data."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise RuntimeError("This command should only be run in a development environment.")
        self.stdout.write("Loading development data...")
        summary = load_fixtures_impl()
        self.stdout.write(self.style.SUCCESS(", ".join(f"{name}: {count}" for name, count in summary.items())))


@transaction.atomic
def load_fixtures_impl(*, now: datetime | None = None) -> dict[str, int]:
    """Create deterministic, interrelated data for development and reporting."""
    fixture_now = now or timezone.now()
    fake = Faker(["en-US"])
    fake.seed_instance(FIXTURE_SEED)
    rng = random.Random(FIXTURE_SEED)

    admin = User.objects.create_superuser(
        name="Admin",
        email="admin@admin.com",
        slug="admin",
        timezone="America/Los_Angeles",
    )
    keepers = _create_keepers(fake)
    participants = _create_participants(fake, fixture_now)
    categories = _create_categories(fake)
    spaces = _create_spaces(fake, rng, keepers, participants, categories)
    _create_sessions(fixture_now, spaces, participants)
    _create_content(fake, fixture_now, admin, keepers, participants)

    return {
        "users": User.objects.count(),
        "onboarding profiles": OnboardModel.objects.count(),
        "spaces": Space.objects.count(),
        "sessions": Session.objects.count(),
        "joined sessions": Session.objects.filter(joined__isnull=False).distinct().count(),
        "session feedback": SessionFeedback.objects.count(),
    }


def _create_keepers(fake: Faker) -> list[User]:
    keepers: list[User] = []
    locations = ("Oakland, CA", "Denver, CO", "Chicago, IL", "Brooklyn, NY", "Portland, OR")
    for index in range(KEEPER_COUNT):
        keeper = User.objects.create_user(
            name=fake.name(),
            email=f"keeper{index + 1:02d}@example.com",
            slug=f"keeper-{index + 1:02d}",
            is_staff=True,
            timezone=TIMEZONES[index],
            newsletter_consent=True,
        )
        KeeperProfile.objects.create(
            user=keeper,
            username=f"keeper_{index + 1:02d}",
            bio=fake.paragraph(nb_sentences=6),
            location=locations[index],
            languages="English" if index < 4 else "English, Spanish",
        )
        keepers.append(keeper)
    return keepers


def _create_participants(fake: Faker, now: datetime) -> list[User]:
    participants: list[User] = []
    referral_sources = [choice.value for choice in ReferralChoices]
    birth_years = (1952, 1960, 1968, 1975, 1982, 1988, 1994, 1999, 2003, 2008)

    for index in range(PARTICIPANT_COUNT):
        joined_at = now - timedelta(days=30 * (index + 1))
        participant = User.objects.create_user(
            name=fake.name(),
            email=f"participant{index + 1:02d}@example.com",
            slug=f"participant-{index + 1:02d}",
            timezone=TIMEZONES[index % len(TIMEZONES)],
            newsletter_consent=index % 3 != 0,
        )
        User.objects.filter(pk=participant.pk).update(date_created=joined_at, date_joined=joined_at)

        completed_onboarding = index < PARTICIPANT_COUNT - 3
        onboarding = OnboardModel.objects.create(
            user=participant,
            onboarded=completed_onboarding,
            year_born=birth_years[index % len(birth_years)] if completed_onboarding else None,
            hopes=fake.sentence() if completed_onboarding else "",
            referral_source=referral_sources[index % len(referral_sources)],
            referral_other="A local community event" if index % len(referral_sources) == 8 else "",
        )
        OnboardModel.objects.filter(pk=onboarding.pk).update(created=joined_at, updated=joined_at)
        participants.append(participant)

    return participants


def _create_categories(fake: Faker) -> list[SpaceCategory]:
    return [
        SpaceCategory.objects.create(name=name, slug=slug, description=fake.paragraph(nb_sentences=4))
        for name, slug in CATEGORY_DATA
    ]


def _create_spaces(
    fake: Faker,
    rng: random.Random,
    keepers: list[User],
    participants: list[User],
    categories: list[SpaceCategory],
) -> list[Space]:
    spaces: list[Space] = []
    for index, title in enumerate(SPACE_TITLES):
        space = Space.objects.create(
            slug=f"space-{index + 1:02d}",
            published=index != len(SPACE_TITLES) - 1,
            open=index % 4 != 3,
            title=title,
            subtitle=fake.sentence(),
            author=keepers[index % len(keepers)],
            content=fake.paragraph(nb_sentences=8),
            recurring="Every week" if index % 2 == 0 else "Twice a month",
            meeting_provider=(
                Space.MeetingProviderChoices.LIVEKIT if index % 2 == 0 else Space.MeetingProviderChoices.GOOGLE_MEET
            ),
        )
        space.categories.add(categories[index % len(categories)], categories[(index + 2) % len(categories)])
        space.tags.add("community", "support", categories[index % len(categories)].slug)
        space.subscribed.add(space.author, *rng.sample(participants, 8))
        spaces.append(space)
    return spaces


def _create_sessions(now: datetime, spaces: list[Space], participants: list[User]) -> None:
    for space_index, space in enumerate(spaces):
        for session_index, day_offset in enumerate(SESSION_DAY_OFFSETS):
            start = now + timedelta(days=day_offset, hours=(space_index % 3) - 1)
            is_past = start + timedelta(minutes=60) < now
            interaction = (space_index + session_index) % 6
            cancelled = is_past and interaction == 5
            session = Session.objects.create(
                slug=f"session-{space_index + 1:02d}-{session_index + 1:02d}",
                space=space,
                title=f"{space.title} #{session_index + 1}",
                start=start,
                duration_minutes=60,
                meeting_url=f"https://meet.example.com/{space.slug}/{session_index + 1}",
                seats=6 + (session_index % 3),
                listed=session_index % 7 != 0,
                open=day_offset > 0,
                cancelled=cancelled,
                ended_at=(
                    start + timedelta(minutes=60)
                    if is_past and not cancelled and space.meeting_provider == Space.MeetingProviderChoices.LIVEKIT
                    else None
                ),
            )
            selected = [
                participants[(space_index * 3 + session_index + offset) % len(participants)] for offset in range(4)
            ]
            session.attendees.add(space.author, *selected)

            if not is_past or cancelled:
                continue

            joined = _joined_users(interaction, space.author, selected)
            session.joined.add(*joined)
            _create_session_feedback(session, space.author, joined, session_index)
            if space.meeting_provider == Space.MeetingProviderChoices.LIVEKIT:
                _create_ended_room(session, joined)


def _joined_users(interaction: int, keeper: User, participants: list[User]) -> list[User]:
    match interaction:
        case 0:
            return [keeper]
        case 1:
            return [keeper, participants[0]]
        case 2:
            return [keeper, *participants[:3]]
        case 3:
            return participants[:1]
        case 4:
            return [keeper, *participants[:2]]
        case _:
            return []


def _create_session_feedback(session: Session, keeper: User, joined: list[User], session_index: int) -> None:
    beneficiaries = [user for user in joined if user != keeper]
    for index, participant in enumerate(beneficiaries):
        if (session_index + index) % 2:
            continue
        negative = (session_index + index) % 5 == 0
        SessionFeedback.objects.create(
            session=session,
            user=participant,
            feedback=SessionFeedbackOptions.DOWN if negative else SessionFeedbackOptions.UP,
            message="I had trouble with the audio." if negative else "",
        )


def _create_ended_room(session: Session, joined: list[User]) -> None:
    room = Room.objects.create(
        session=session,
        status=RoomStatus.ENDED,
        turn_state=TurnState.IDLE,
        keeper=session.space.author.slug,
        talking_order=[user.slug for user in joined],
        round_number=2,
        state_version=2,
        end_reason=EndReason.KEEPER_ENDED,
    )
    snapshot = room.to_state().model_dump(mode="json")
    RoomEventLog.objects.create(room=room, version=1, event_type="start_room", actor=room.keeper, snapshot=snapshot)
    RoomEventLog.objects.create(room=room, version=2, event_type="end_room", actor=room.keeper, snapshot=snapshot)


def _create_content(
    fake: Faker,
    now: datetime,
    admin: User,
    keepers: list[User],
    participants: list[User],
) -> None:
    for index in range(4):
        BlogPost.objects.create(
            slug=f"development-post-{index + 1}",
            title=f"Development Blog Post {index + 1}",
            subtitle=fake.sentence(),
            summary=fake.paragraph(nb_sentences=2),
            author=keepers[index % len(keepers)],
            content=f"## A development post\n\n{fake.paragraph(nb_sentences=10)}",
            date_published=now - timedelta(days=index * 45),
            publish=index < 3,
        )

    CoursePage.objects.create(
        title="Keeper Guide",
        slug="keeper-guide",
        enable_toc=True,
        created_by=admin,
        content=f"## Welcome\n\n{fake.paragraph(nb_sentences=12)}",
    )
    CoursePage.objects.create(
        title="Session Facilitation Checklist",
        slug="facilitation-checklist",
        created_by=admin,
        content=f"## Before the session\n\n{fake.paragraph(nb_sentences=8)}",
    )

    for index in range(3):
        CirclePlan.objects.create(
            name=f"Development Plan {index + 1}",
            description=fake.paragraph(nb_sentences=3),
            content=fake.paragraph(nb_sentences=8),
            display_date=now - timedelta(days=index * 30),
            published=index < 2,
            created_by=admin,
        )

    prompt_tags = ("opening", "reflection", "community", "closing")
    for index in range(12):
        prompt = Prompt.objects.create(
            prompt=fake.sentence(nb_words=12).rstrip(".") + "?",
            created_by=keepers[index % len(keepers)],
            notes="Development prompt",
        )
        prompt.tags.add(prompt_tags[index % len(prompt_tags)])

    for index in range(3):
        Redirect.objects.create(
            slug=f"development-redirect-{index + 1}",
            alternate_slug=f"dev-{index + 1}",
            url=f"/spaces/space-{index + 1:02d}",
            permanent=index == 0,
            notes="Generated development redirect",
            count=index * 12,
        )

    for index, participant in enumerate(participants[:6]):
        Feedback.objects.create(
            user=participant,
            email=participant.email,
            message=fake.paragraph(nb_sentences=3),
        )

    for participant in participants[:10]:
        SubscribedModel.objects.create(user=participant, subscribed=True)

    for index, participant in enumerate(participants[:6]):
        FCMDevice.objects.create(
            user=participant,
            token=f"development-fcm-token-{index + 1}",
            active=index < 5,
            last_used=now - timedelta(days=index),
        )
