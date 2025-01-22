# tests/test_middleware.py
import zoneinfo
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.utils import timezone

from totem.users.tests.factories import UserFactory
from totem.utils.middleware import TimezoneMiddleware

User = get_user_model()


@pytest.fixture
def mock_request():
    request = HttpRequest()
    request.COOKIES = {}
    request.user = Mock()
    request.user.is_authenticated = False
    return request


@pytest.fixture
def middleware():
    return TimezoneMiddleware(get_response=lambda r: None)


def test_timezone_middleware_no_timezone_info(middleware, mock_request):
    """Test middleware when no timezone information is available"""
    middleware(mock_request)
    assert timezone.get_current_timezone() == zoneinfo.ZoneInfo("UTC")


def test_timezone_middleware_with_cookie(middleware, mock_request):
    """Test middleware with timezone cookie"""
    mock_request.COOKIES["totem_timezone"] = "America/New_York"
    middleware(mock_request)
    assert timezone.get_current_timezone() == zoneinfo.ZoneInfo("America/New_York")


def test_timezone_middleware_with_invalid_cookie(middleware, mock_request):
    """Test middleware with invalid timezone cookie"""
    mock_request.COOKIES["totem_timezone"] = "Invalid/Timezone"
    middleware(mock_request)
    assert timezone.get_current_timezone() == zoneinfo.ZoneInfo("UTC")


def test_timezone_middleware_with_authenticated_user(middleware, mock_request):
    """Test middleware with authenticated user having timezone set"""
    mock_request.user.is_authenticated = True
    mock_request.user.timezone = zoneinfo.ZoneInfo("Europe/London")
    middleware(mock_request)
    assert timezone.get_current_timezone() == zoneinfo.ZoneInfo("Europe/London")


def test_timezone_middleware_authenticated_user_no_timezone(middleware, mock_request):
    """Test middleware with authenticated user but no timezone set"""
    mock_request.user.is_authenticated = True
    mock_request.user.timezone = None
    mock_request.COOKIES["totem_timezone"] = "Asia/Tokyo"

    middleware(mock_request)

    assert timezone.get_current_timezone() == zoneinfo.ZoneInfo("Asia/Tokyo")
    assert mock_request.user.timezone == zoneinfo.ZoneInfo("Asia/Tokyo")
    mock_request.user.save.assert_called_once()


def test_timezone_middleware_authenticated_user_updates_timezone(middleware, mock_request):
    """Test middleware updates authenticated user's timezone from cookie"""
    mock_request.user.is_authenticated = True
    mock_request.user.timezone = None
    mock_request.COOKIES["totem_timezone"] = "Australia/Sydney"

    middleware(mock_request)

    assert mock_request.user.timezone == zoneinfo.ZoneInfo("Australia/Sydney")
    mock_request.user.save.assert_called_once()


def test_timezone_middleware_authenticated_user_updates_timezone_with_timezone_set(middleware, mock_request):
    """Test middleware updates authenticated user's timezone from cookie"""
    mock_request.user.is_authenticated = True
    mock_request.user.timezone = zoneinfo.ZoneInfo("Asia/Tokyo")
    mock_request.COOKIES["totem_timezone"] = "Australia/Sydney"

    middleware(mock_request)

    assert mock_request.user.timezone == zoneinfo.ZoneInfo("Australia/Sydney")
    mock_request.user.save.assert_called_once()


@pytest.mark.django_db
def test_timezone_middleware_integration():
    """Integration test with actual User model"""
    user = UserFactory(email="test@example.com")
    user.timezone = zoneinfo.ZoneInfo("Europe/Paris")
    user.save()

    request = HttpRequest()
    request.user = user

    middleware = TimezoneMiddleware(get_response=lambda r: None)
    middleware(request)

    assert timezone.get_current_timezone() == zoneinfo.ZoneInfo("Europe/Paris")
