from __future__ import annotations

import logging

import firebase_admin
from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone
from firebase_admin import credentials, messaging

from totem.notifications.models import FCMDevice
from totem.notifications.schemas import SessionNotificationPayload
from totem.users.models import User

logger = logging.getLogger(__name__)


def initialize_firebase() -> bool:
    """
    Initialize Firebase Admin SDK if not already initialized.
    Uses Firebase's built-in app detection instead of a manual flag.
    """
    try:
        # Check if already initialized
        firebase_admin.get_app()
        return True
    except ValueError:
        # Not initialized yet
        pass

    if not settings.FIREBASE_FCM_CREDENTIALS_SECRET_JSON_B64:
        logger.error("No Firebase credentials configured")
        return False

    try:
        cred = credentials.Certificate(settings.FIREBASE_FCM_CREDENTIALS_SECRET_JSON_B64)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase initialized")
        return True
    except Exception as e:
        logger.error("Failed to initialize Firebase (%s)", type(e).__name__)
        return False


def send_notification_to_user(
    user: User, title: str, body: str, data: SessionNotificationPayload | None = None
) -> bool:
    """
    Send notification to all active devices of a specific user

    Args:
        user: The user to send notification to
        title: Notification title
        body: Notification body
        data: Additional data payload

    Returns:
        bool: True if notification was sent to at least one device
    """

    return send_notification_to_devices(FCMDevice.objects.filter(user=user, active=True), title, body, data)


def send_notification_to_devices(
    devices: QuerySet[FCMDevice], title: str, body: str, data: SessionNotificationPayload | None = None
) -> bool:
    active_devices = list(devices.filter(active=True))
    if not active_devices:
        return False
    return send_notification([device.fid for device in active_devices], title, body, data, devices=active_devices)


def send_notification(
    fids: list[str],
    title: str,
    body: str,
    data: SessionNotificationPayload | None = None,
    *,
    devices: list[FCMDevice] | None = None,
) -> bool:
    """
    Send notification to specific Firebase Installation IDs

    Args:
        fids: list of Firebase Installation IDs
        title: Notification title
        body: Notification body
        data: Additional data payload

    Returns:
        bool: True if notification was sent to at least one device
    """
    if not fids:
        return False

    try:
        data_payload = data.model_dump(mode="json", exclude_none=True) if data is not None else {}
        if not isinstance(data_payload, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or key in {"from", "message_type", "collapse_key"}
            or key.startswith(("google.", "gcm."))
            for key, value in data_payload.items()
        ):
            raise ValueError("Invalid FCM data")
        size = sum(len(key.encode("utf-8")) + len(value.encode("utf-8")) for key, value in data_payload.items())
        size += len("title") + len(title.encode("utf-8")) + len("body") + len(body.encode("utf-8"))
        if size > 4096:
            raise ValueError("FCM payload exceeds size limit")
    except Exception as e:
        logger.error("Invalid FCM notification data (%s)", type(e).__name__)
        return False

    if not initialize_firebase():
        return False

    if devices is None:
        devices = list(FCMDevice.objects.filter(fid__in=fids, active=True))

    successful_fids: set[str] = set()
    invalid_fids: set[str] = set()

    for fid in fids:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body), data=data_payload, fid=fid
            )
            messaging.send(message)
            successful_fids.add(fid)
        except messaging.UnregisteredError:
            invalid_fids.add(fid)
            logger.info("Unregistered FCM device marked inactive")
        except messaging.SenderIdMismatchError:
            logger.error("FCM sender ID mismatch; check Firebase project credentials")
        except messaging.ThirdPartyAuthError:
            # This is a server configuration problem, not an invalid device.
            logger.error("FCM third-party authentication failed (APNs/Web Push)")
        except Exception as e:
            # Do not deactivate devices for server-side errors.
            logger.error("Failed to send FCM notification (%s)", type(e).__name__)

    for device in devices:
        # Registration may have changed while the network request was in flight.
        current = FCMDevice.objects.filter(
            pk=device.pk,
            user_id=device.user_id,
            fid=device.fid,
            updated_at=device.updated_at,
            active=True,
        )
        if device.fid in successful_fids:
            current.update(last_used=timezone.now())
        elif device.fid in invalid_fids:
            current.update(active=False)

    return bool(successful_fids)
