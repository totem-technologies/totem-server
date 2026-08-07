from datetime import datetime
from datetime import timezone as dt_timezone

import pytest
from django.db.models import Count

from totem.blog.models import BlogPost
from totem.course.models import CoursePage
from totem.email.models import SubscribedModel
from totem.notifications.models import FCMDevice
from totem.onboard.models import OnboardModel
from totem.pages.models import Redirect
from totem.plans.models import CirclePlan
from totem.repos.models import Prompt
from totem.rooms.models import Room, RoomEventLog
from totem.spaces.models import Session, SessionFeedback
from totem.users.models import Feedback, KeeperProfile, User
from totem.utils.management.commands.load_dev_data import load_fixtures_impl

pytestmark = pytest.mark.django_db


def test_loads_representative_interactions_and_content():
    now = datetime(2026, 8, 3, 12, tzinfo=dt_timezone.utc)

    load_fixtures_impl(now=now)

    assert User.objects.filter(is_staff=False).count() >= 20
    assert KeeperProfile.objects.count() >= 3
    assert OnboardModel.objects.filter(onboarded=True, year_born__isnull=False).exists()
    assert OnboardModel.objects.filter(onboarded=False).exists()

    completed = Session.objects.filter(start__lt=now, cancelled=False)
    assert completed.exists()
    assert Session.objects.filter(start__gt=now).exists()
    assert Session.objects.filter(cancelled=True).exists()

    keeper_only = [
        session
        for session in completed.select_related("space__author").prefetch_related("joined")
        if set(session.joined.values_list("pk", flat=True)) == {session.space.author_id}
    ]
    successful = [
        session
        for session in completed.select_related("space__author").prefetch_related("joined")
        if session.joined.exclude(pk=session.space.author_id).exists()
    ]
    participant_only = [
        session
        for session in successful
        if session.joined.count() == 1 and not session.joined.filter(pk=session.space.author_id).exists()
    ]
    assert keeper_only
    assert successful
    assert participant_only

    assert any(
        set(session.attendees.values_list("pk", flat=True)) - set(session.joined.values_list("pk", flat=True))
        for session in completed.prefetch_related("attendees", "joined")
    )
    assert User.objects.annotate(session_count=Count("sessions_joined")).filter(session_count__gt=1).exists()
    assert SessionFeedback.objects.exists()
    assert Room.objects.exists()
    assert RoomEventLog.objects.exists()

    assert BlogPost.objects.exists()
    assert CoursePage.objects.exists()
    assert CirclePlan.objects.exists()
    assert Prompt.objects.exists()
    assert Redirect.objects.exists()
    assert Feedback.objects.exists()
    assert SubscribedModel.objects.exists()
    assert FCMDevice.objects.exists()
