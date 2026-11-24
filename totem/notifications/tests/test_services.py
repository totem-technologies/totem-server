import json
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from firebase_admin import messaging
from firebase_admin._messaging_encoder import MessageEncoder

from totem.notifications.models import FCMDevice
from totem.notifications.schemas import NotificationType, SessionNotificationPayload
from totem.notifications.services import send_notification, send_notification_to_user
from totem.users.tests.factories import UserFactory


@pytest.fixture
def mock_firebase_initialized():
    with patch("totem.notifications.services.initialize_firebase", return_value=True) as mock_init:
        yield mock_init


@pytest.mark.django_db
class TestNotificationServices:
    @pytest.mark.parametrize(
        "payload_data",
        [
            {"google.secret": "value"},
            {"gcm.secret": "value"},
            {"from": "value"},
            {"message_type": "value"},
            {"collapse_key": "value"},
            {"nested": {"value": "bad"}},
            {"number": 1},
            {"large": "é" * 2046},
        ],
    )
    @patch("totem.notifications.services.messaging.send")
    def test_invalid_payload_is_contained(self, mock_send, payload_data, mock_firebase_initialized):
        payload = MagicMock()
        payload.model_dump.return_value = payload_data
        assert not send_notification(["fid"], "title", "body", payload)
        mock_send.assert_not_called()

    @patch("totem.notifications.services.messaging.send")
    def test_serialization_error_is_contained(self, mock_send, mock_firebase_initialized, caplog):
        payload = MagicMock()
        payload.model_dump.side_effect = ValueError("private-payload")
        assert not send_notification(["fid"], "title", "body", payload)
        mock_send.assert_not_called()
        assert "private-payload" not in caplog.text

    @patch("totem.notifications.services.messaging.send")
    def test_payload_size_boundary(self, mock_send, mock_firebase_initialized):
        payload = MagicMock()
        payload.model_dump.return_value = {"key": "a" * 4075}
        assert send_notification(["fid"], "title", "body", payload)
        payload.model_dump.return_value = {"key": "a" * 4076}
        assert not send_notification(["fid"], "title", "body", payload)
        mock_send.assert_called_once()

    @patch("totem.notifications.services.messaging.send")
    def test_payload_serialized_to_fid_message(self, mock_send, mock_firebase_initialized):
        payload = SessionNotificationPayload(
            type=NotificationType.SESSION_STARTING, space_slug="space", session_slug="session"
        )
        assert send_notification(["fid"], "title", "body", payload)
        message = mock_send.call_args.args[0]
        assert message.fid == "fid" and message.token is None
        encoded = json.loads(json.dumps(message, cls=MessageEncoder))
        assert encoded["fid"] == "fid"
        assert encoded["data"] == message.data
        assert message.data == {"type": "session_starting", "space_slug": "space", "session_slug": "session"}

    @patch("totem.notifications.services.messaging.send")
    def test_delivery_isolates_failures_and_only_updates_targeted_devices(
        self, mock_send, mock_firebase_initialized, caplog
    ):
        user = UserFactory()
        invalid = FCMDevice.objects.create(user=user, fid="private-invalid")
        success = FCMDevice.objects.create(user=user, fid="private-success")
        inactive = FCMDevice.objects.create(user=user, fid="private-inactive", active=False)
        other = FCMDevice.objects.create(user=UserFactory(), fid="private-other")

        def send(message):
            if message.fid == invalid.fid:
                raise messaging.UnregisteredError("private-invalid")
            return "ok"

        mock_send.side_effect = send
        caplog.set_level("INFO", logger="totem.notifications.services")
        assert send_notification_to_user(user, "title", "body")
        assert {call.args[0].fid for call in mock_send.call_args_list} == {invalid.fid, success.fid}
        for device in (invalid, success, inactive, other):
            device.refresh_from_db()
        assert not invalid.active and invalid.last_used is None
        assert success.active and success.last_used is not None
        assert not inactive.active and inactive.last_used is None
        assert other.active and other.last_used is None
        assert "private-invalid" not in caplog.text and "private-success" not in caplog.text

    @pytest.mark.parametrize(
        "error",
        [messaging.SenderIdMismatchError, messaging.ThirdPartyAuthError, messaging.QuotaExceededError, Exception],
    )
    @patch("totem.notifications.services.messaging.send")
    def test_non_device_failures_remain_active_and_do_not_log_secrets(
        self, mock_send, error, mock_firebase_initialized, caplog
    ):
        device = FCMDevice.objects.create(user=UserFactory(), fid="private-identifier")
        mock_send.side_effect = error("private-identifier private-payload")
        assert not send_notification_to_user(device.user, "title", "private-payload")
        device.refresh_from_db()
        assert device.active and device.last_used is None
        assert "private-identifier" not in caplog.text and "private-payload" not in caplog.text

    @pytest.mark.parametrize("reassign", [False, True])
    @patch("totem.notifications.services.messaging.send")
    def test_registration_changed_during_send_is_not_deactivated(self, mock_send, reassign, mock_firebase_initialized):
        device = FCMDevice.objects.create(user=UserFactory(), fid="private-fid")
        original_user = device.user

        def send(message):
            if reassign:
                device.delete()
                FCMDevice.objects.create(user=UserFactory(), fid=message.fid)
            else:
                FCMDevice.objects.filter(pk=device.pk).update(updated_at=timezone.now())
            raise messaging.UnregisteredError("unregistered")

        mock_send.side_effect = send
        assert not send_notification_to_user(original_user, "title", "body")
        assert FCMDevice.objects.get(fid=device.fid).active

    @patch("totem.notifications.services.messaging.send")
    def test_user_without_active_devices_is_not_sent(self, mock_send, mock_firebase_initialized):
        user = UserFactory()
        FCMDevice.objects.create(user=user, fid="inactive", active=False)
        assert not send_notification_to_user(user, "title", "body")
        mock_send.assert_not_called()
