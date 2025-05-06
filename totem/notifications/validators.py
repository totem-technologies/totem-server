import re
from ninja.errors import ValidationError


def validate_fcm_token(token):
    """
    Validate FCM token format

    Raises:
        ValidationError: With machine-readable error code if validation fails
    """
    if not token or not isinstance(token, str):
        raise ValidationError(errors=[{"token": "INVALID_TOKEN"}])

    # FCM tokens are typically 140+ characters
    if len(token) < 140:
        raise ValidationError(errors=[{"token": "INVALID_TOKEN"}])

    # Basic pattern checking for FCM tokens
    if not re.match(r"^[a-zA-Z0-9:_-]+$", token):
        raise ValidationError(errors=[{"token": "INVALID_TOKEN"}])

    return True
