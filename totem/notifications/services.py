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
        if hasattr(settings, "FIREBASE_CREDENTIALS_FILE"):
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_FILE)
        elif hasattr(settings, "FIREBASE_CREDENTIALS"):
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS)
        else:
            logger.error("No Firebase credentials configured")
            return False

        firebase_admin.initialize_app(cred, name=getattr(settings, "FIREBASE_APP_NAME", "totem"))
        _firebase_initialized = True
        return True
    return True


def send_notification_to_user(user: User, title: str, body: str, data: Optional[Dict[str, str]] = None) -> bool:
    """
    Send notification to all active devices of a specific user

    Args:
        user_id: The user ID to send notification to
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

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        tokens=tokens,
    )

    response: messaging.BatchResponse = messaging.send_multicast(message)

    responses: list[messaging.SendResponse] = response.responses
    for idx, result in enumerate(responses):
        if result.success:
            FCMDevice.objects.filter(token=tokens[idx]).update(last_used=timezone.now())
        else:
            # Mark failed tokens as inactive
            FCMDevice.objects.filter(token=tokens[idx]).update(active=False)

    return response.success_count > 0


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
