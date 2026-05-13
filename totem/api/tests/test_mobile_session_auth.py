"""Tests for the session-cookie auth fallback on the mobile router.

The mobile router accepts both JWT bearer (native Flutter app) and Django
session + CSRF (Flutter web build at /room/). These tests cover the session
path; JWT coverage lives in the existing mobile/ tests.
"""

from django.test import Client
from django.urls import reverse

from totem.users.tests.factories import UserFactory


def test_user_current_via_session_cookie(client: Client, db):
    user = UserFactory(name="Cookie User")
    client.force_login(user)

    response = client.get(reverse("mobile-api:user_current"))

    assert response.status_code == 200
    assert response.json()["name"] == "Cookie User"


def test_user_update_via_session_cookie(client: Client, db):
    user = UserFactory(name="Old Name")
    client.force_login(user)

    response = client.post(
        reverse("mobile-api:user_update"),
        data={"name": "New Name"},
        content_type="application/json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.name == "New Name"


def test_user_update_unauthenticated(client: Client, db):
    response = client.post(
        reverse("mobile-api:user_update"),
        data={"name": "Anything"},
        content_type="application/json",
    )

    assert response.status_code == 401


def test_user_update_csrf_enforced_for_session(db):
    """A logged-in browser without the CSRF token must be rejected."""
    user = UserFactory(name="Old Name")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.post(
        reverse("mobile-api:user_update"),
        data={"name": "New Name"},
        content_type="application/json",
    )

    assert response.status_code == 403
    user.refresh_from_db()
    assert user.name == "Old Name"
