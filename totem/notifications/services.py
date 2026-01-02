import logging
from typing import Dict, List, Optional

import firebase_admin
from django.conf import settings
from django.utils import timezone
from firebase_admin import credentials, messaging

from totem.notifications.models import FCMDevice
from totem.users.models import User

logger = logging.getLogger(__name__)


def initialize_firebase():
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
        logger.error("Failed to initialize Firebase: %s", e)
        return False


def send_notification_to_user(user: User, title: str, body: str, data: Optional[Dict[str, str]] = None) -> bool:
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

    devices = FCMDevice.objects.filter(user=user, active=True)
    if not devices.exists():
        return False

    tokens = list(devices.values_list("token", flat=True))
    return send_notification(tokens, title, body, data)


def send_notification(tokens: List[str], title: str, body: str, data: Optional[Dict[str, str]] = None) -> bool:
    """
    Send notification to specific FCM tokens

    Args:
        tokens: List of FCM tokens
        title: Notification title
        body: Notification body
        data: Additional data payload

    Returns:
        bool: True if notification was sent to at least one device
    """
    if not tokens:
        return False

    if not initialize_firebase():
        return False

    notification = messaging.Notification(
        title=title,
        body=body,
    )
    data_payload = data or {}

    success_count = 0
    invalid_tokens = []  # Tokens that are no longer valid (should be deactivated)
    successful_tokens = []

    for token in tokens:
        message = messaging.Message(notification=notification, data=data_payload, token=token)

        try:
            messaging.send(message)
            success_count += 1
            successful_tokens.append(token)
        except messaging.UnregisteredError:
            # Token is no longer valid - mark for deactivation
            invalid_tokens.append(token)
            logger.info("FCM token invalid and marked as inactive: %s...", token[:20])
        except messaging.SenderIdMismatchError:
            # Token was registered with a different sender - mark for deactivation
            invalid_tokens.append(token)
            logger.warning("FCM token sender mismatch: %s...", token[:20])
        except Exception as e:
            # Don't deactivate token for server-side errors (auth issues, network, etc.)
            logger.error("Failed to send FCM notification (%s): %s", type(e).__name__, e)

    # Bulk update the device records to avoid individual DB queries
    if successful_tokens:
        FCMDevice.objects.filter(token__in=successful_tokens).update(last_used=timezone.now())

    if invalid_tokens:
        FCMDevice.objects.filter(token__in=invalid_tokens).update(active=False)

    return success_count > 0
