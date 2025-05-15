import logging
from typing import Dict, List, Optional

import firebase_admin
from django.conf import settings
from django.utils import timezone
from firebase_admin import credentials, messaging

from totem.notifications.models import FCMDevice
from totem.users.models import User

logger = logging.getLogger(__name__)

# Firebase initialization flag
_firebase_initialized = False


def initialize_firebase():
    """
    Initialize Firebase Admin SDK if not already initialized
    """
    global _firebase_initialized
    if not _firebase_initialized:
        if settings.FIREBASE_FCM_CREDENTIALS_JSON_B64:
            cred = credentials.Certificate(settings.FIREBASE_FCM_CREDENTIALS_JSON_B64)
        else:
            logger.error("No Firebase credentials configured")
            return False

        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("Firebase initialized")
        return True
    return True


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
    if not initialize_firebase():
        return False

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
    failed_tokens = []
    successful_tokens = []

    for token in tokens:
        message = messaging.Message(notification=notification, data=data_payload, token=token)

        try:
            messaging.send(message)
            success_count += 1
            successful_tokens.append(token)
        except messaging.UnregisteredError:
            # Token is no longer valid
            failed_tokens.append(token)
            logger.info(f"FCM token invalid and marked as inactive: {token}")
        except Exception as e:
            failed_tokens.append(token)
            logger.error(f"Failed to send FCM notification: {str(e)}")

    # Bulk update the device records to avoid individual DB queries
    if successful_tokens:
        FCMDevice.objects.filter(token__in=successful_tokens).update(last_used=timezone.now())

    if failed_tokens:
        FCMDevice.objects.filter(token__in=failed_tokens).update(active=False)

    return success_count > 0


def validate_fcm_token(token: str) -> bool:
    """
    Validate FCM token with Firebase by doing a dry run

    Args:
        token: FCM token to validate

    Returns:
        bool: True if token is valid
    """
    if not initialize_firebase():
        return False

    try:
        # Create a message targeting the token
        message = messaging.Message(data={"validation": "true"}, token=token)

        # Perform a dry run (validation only, no actual message sent)
        messaging.send(message, dry_run=True)
        return True
    except messaging.UnregisteredError:
        # Token is invalid or has been unregistered
        return False
