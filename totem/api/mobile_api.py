import jwt
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router
from ninja.errors import ValidationError
from ninja.security import HttpBearer

from totem.blog.mobile_api import blog_router
from totem.meetings.mobile_api import meetings_router
from totem.notifications.models import FCMDevice
from totem.notifications.schemas import FCMTokenRegisterSchema, FCMTokenResponseSchema
from totem.notifications.validators import validate_fcm_token
from totem.onboard.mobile_api import onboard_router
from totem.spaces.mobile_api.mobile_api import spaces_router
from totem.users.mobile_api import user_router
from totem.users.models import User

from .auth import JWTSchema


class JWTAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> User | None:
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

    # Delete any devices with this token belonging to other users
    FCMDevice.objects.filter(token=payload.token).exclude(user=request.user).delete()

    # Create or update the device for the current user atomically
    device, _ = FCMDevice.objects.update_or_create(
        token=payload.token,
        user=request.user,
        defaults={"active": True, "updated_at": timezone.now()},
    )

    return 201, device


@router.delete("/fcm/unregister/{token}", response={204: None}, url_name="unregister_fcm_token")
def unregister_fcm_token(request: HttpRequest, token: str):
    """Delete an FCM token for the current user"""
    device = FCMDevice.objects.filter(token=token, user=request.user).first()
    if device:
        device.delete()
    return 204, None
