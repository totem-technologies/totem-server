# Create your tests here.
from datetime import datetime

import pytest

from totem.onboard.models import OnboardModel
from totem.onboard.views import OnboardForm
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_onboard_form_valid(db):
    user = UserFactory()
    form_data = {
        "name": "John",
        "age": 25,
        "hopes": "I hope to learn a lot!",
    }
    form = OnboardForm(data=form_data)
    assert form.is_valid()
    onboard = OnboardModel(user=user)
    form.save(user=user, onboard=onboard)
    assert user.name == "John"
    assert onboard.year_born == datetime.now().year - 25
    assert onboard.hopes == "I hope to learn a lot!"
    assert onboard.onboarded is True


def test_onboard_form_invalid(db):
    form_data = {
        "name": "",
        "age": 10,
        "hopes": "I hope to learn a lot!",
    }
    form = OnboardForm(data=form_data)
    assert not form.is_valid()
    assert "name" in form.errors
    assert "age" in form.errors
    assert "hopes" not in form.errors
