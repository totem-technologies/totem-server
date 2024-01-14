import pytest
from pytest_socket import disable_socket

from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()


def pytest_runtest_setup():
    disable_socket()
