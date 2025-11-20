from typing import Optional

import jwt
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router
from ninja.errors import ValidationError
from ninja.security import HttpBearer

from totem.blog.mobile_api import blog_router
from totem.circles.mobile_api.mobile_api import spaces_router
from totem.meetings.mobile_api import meetings_router
from totem.notifications.models import FCMDevice
from totem.notifications.schemas import FCMTokenRegisterSchema, FCMTokenResponseSchema
from totem.notifications.validators import validate_fcm_token
from totem.onboard.mobile_api import onboard_router
from totem.users.mobile_api import user_router
from totem.users.models import User

from .auth import JWTSchema


class JWTAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> Optional[User]:
        try:
            # Decode JWT token
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            data = JWTSchema(**payload)

            # Check if token is expired
            if not data.exp or timezone.now() > data.exp:
                return None

            # Get user
            try:
                user = User.objects.get(api_key=data.api_key, pk=data.pk)

                # Check if user is active
                if not user.is_active:
                    return None
                request.user = user
                return user
            except User.DoesNotExist:
                return None
        except jwt.PyJWTError:
            return None


# Create router
router = Router(auth=JWTAuth())
router.add_router("/users", user_router)
router.add_router("/onboard", onboard_router)
router.add_router("/spaces", spaces_router)
router.add_router("/blog", blog_router)
router.add_router("/meetings", meetings_router)


@router.post("/fcm/register", response={201: FCMTokenResponseSchema}, url_name="register_fcm_token")
def register_fcm_token(request: HttpRequest, payload: FCMTokenRegisterSchema):
    """Register or update an FCM token for the current user"""
    # Validate token format
    valid = validate_fcm_token(payload.token)
    if not valid:
        raise ValidationError(errors=[{"token": "INVALID_TOKEN"}])

    # Check for existing devices with this token
    existing_devices = FCMDevice.objects.filter(token=payload.token)

    if existing_devices.count() > 1:
        # Multiple devices with same token - delete all and create new
        existing_devices.delete()
        device = FCMDevice.objects.create(token=payload.token, user=request.user, active=True)
    elif device := existing_devices.first():
        # Single existing device - update it
        device.user = request.user
        device.active = True
        device.updated_at = timezone.now()
        device.save()
    else:
        # No existing device - create new
        device = FCMDevice.objects.create(token=payload.token, user=request.user, active=True)

    return 201, device


@router.delete("/fcm/unregister/{token}", response={204: None}, url_name="unregister_fcm_token")
def unregister_fcm_token(request: HttpRequest, token: str):
    """Delete an FCM token for the current user"""
    device = FCMDevice.objects.filter(token=token, user=request.user).first()
    if device:
        device.delete()
    return 204, None
