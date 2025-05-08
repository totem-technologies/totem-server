import logging
from datetime import timedelta

from django.utils import timezone

from totem.notifications.models import FCMDevice
from totem.notifications.services import validate_fcm_token

logger = logging.getLogger(__name__)


def verify_fcm_tokens():
    """
    Verify FCM tokens to ensure they are still valid.
    Mark invalid tokens as inactive.

    This should be run periodically to clean up stale tokens.
    """
    # Get tokens older than 30 days or that have never been verified
    cutoff_date = timezone.now() - timedelta(days=30)
    devices = FCMDevice.objects.filter(active=True).filter(last_used__lte=cutoff_date)[
        :100
    ]  # Process in batches to avoid timeouts

    valid_count = 0
    invalid_count = 0

    for device in devices:
        if not validate_fcm_token(device.token):
            device.active = False
            invalid_count += 1
        else:
            device.last_used = timezone.now()
            valid_count += 1
        device.save()

    if invalid_count > 0 or valid_count > 0:
        logger.info(f"FCM token verification: {valid_count} valid, {invalid_count} invalidated")


# List of tasks to be run by totem_tasks.py
tasks = [verify_fcm_tokens]
