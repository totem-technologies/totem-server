import uuid

from django.contrib.messages import get_messages

from totem.users.tests.factories import UserFactory

from .. import actions
from ..actions import SubscribeAction
from .factories import CircleFactory


class TestActions:
    def test_join_circle_action(self, db):
        event_slug = "slug"
        user = UserFactory()
        assert user.verified is False
        action = actions.JoinCircleAction(user, parameters={"event_slug": event_slug})
        assert action.action_id == "circles:join"
        url = action.build_url()
        assert f"spaces/join/{event_slug}" in url
        assert "?token=" in url
        # get it back
        token = url.split("?token=")[1]
        action = actions.JoinCircleAction(user, parameters={"event_slug": event_slug})
        user, parameters = action.resolve(token)
        assert user.verified is True
        assert user == user
        assert parameters["event_slug"] == event_slug

    def test_join_expired(self, db):
        event_slug = "slug"
        user = UserFactory()
        action = actions.JoinCircleAction(user, parameters={"event_slug": event_slug})
        url = action.build_url(expires_at="2021-01-01T00:00:00Z")
        token = url.split("?token=")[1]
        try:
            actions.JoinCircleAction.resolve(token)
            assert False
        except actions.JoinCircleAction.ActionExpired:
            assert True
        except Exception:
            assert False

    def test_join_does_not_exists(self, db):
        try:
            actions.JoinCircleAction.resolve(str(uuid.uuid4()))
            assert False
        except actions.JoinCircleAction.ActionDoesNotExist:
            assert True


class TestSubscribeAction:
    def test_subscribe(self, client, db):
        user = UserFactory()
        circle = CircleFactory()
        assert circle.subscribed.count() == 0
        url = SubscribeAction(user=user, parameters={"circle_slug": circle.slug, "subscribe": True}).build_url()
        assert "spaces/subscribe/" in url
        assert circle.slug in url
        token = url.split("token=")[1].split("&")[0]
        user1, params = SubscribeAction.resolve(token)
        assert user1 == user
        assert params
        assert params["circle_slug"] == circle.slug
        assert params["subscribe"] is True
        response = client.get(url)
        circle.refresh_from_db()
        assert circle.subscribed.count() == 1
        message = list(get_messages(response.wsgi_request))[0]
        assert "subscribed" in message.message.lower()

    def test_unsubscribe(self, client, db):
        user = UserFactory()
        circle = CircleFactory()
        circle.subscribed.add(user)
        assert circle.subscribed.count() == 1
        url = SubscribeAction(user=user, parameters={"circle_slug": circle.slug, "subscribe": False}).build_url()
        assert "spaces/subscribe/" in url
        assert circle.slug in url
        token = url.split("token=")[1].split("&")[0]
        user1, params = SubscribeAction.resolve(token)
        assert user1 == user
        assert params
        assert params["circle_slug"] == circle.slug
        assert params["subscribe"] is False

        response = client.get(url)
        circle.refresh_from_db()
        assert circle.subscribed.count() == 0
        message = list(get_messages(response.wsgi_request))[0]
        assert "unsubscribed" in message.message.lower()

    def test_invalid_token(self, client, db):
        user = UserFactory()
        circle = CircleFactory()
        url = SubscribeAction(user=user, parameters={"circle_slug": circle.slug, "subscribe": False}).build_url()
        assert "spaces/subscribe/" in url
        assert circle.slug in url
        token = url.split("token=")[1].split("&")[0]
        token = token[:-1] + "0"
        response = client.get(url[:-3])  # make the token invalid
        assert response.status_code == 302
        assert response.url == f"/spaces/{circle.slug}/"
        message = list(get_messages(response.wsgi_request))[0]
        assert "invalid" in message.message.lower()
