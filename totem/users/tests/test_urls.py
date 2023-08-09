from django.urls import resolve, reverse

from totem.users.models import User


def test_detail(user: User):
    assert reverse("users:detail", kwargs={"slug": user.slug}) == f"/users/{user.slug}/"
    assert resolve(f"/users/{user.slug}/").view_name == "users:detail"


def test_update():
    assert reverse("users:update") == "/users/~update/"
    assert resolve("/users/~update/").view_name == "users:update"


def test_redirect():
    assert reverse("users:redirect") == "/users/~redirect/"
    assert resolve("/users/~redirect/").view_name == "users:redirect"
