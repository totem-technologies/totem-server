import jwt
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status
from ninja.security import HttpBearer, django_auth

from totem.blog.mobile_api import blog_router
from totem.notifications.models import FCMDevice
from totem.notifications.schemas import FCMFIDRegisterSchema, FCMFIDResponseSchema
from totem.notifications.validators import validate_fid
from totem.onboard.mobile_api import onboard_router
from totem.rooms.api import router as rooms_router
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


# Create router. JWTAuth is tried first for the native Flutter app; django_auth
# (session cookie + CSRF) is the fallback used by the Flutter web build hosted
# at /room/ — same endpoints, same shapes, just a different credential.
router = Router(auth=[JWTAuth(), django_auth])
router.add_router("/users", user_router)
router.add_router("/onboard", onboard_router)
router.add_router("/spaces", spaces_router)
router.add_router("/blog", blog_router)
router.add_router("/rooms", rooms_router)


@router.post("/fcm/register", response={201: FCMFIDResponseSchema}, url_name="register_fcm_fid")
def register_fcm_fid(request: HttpRequest, payload: FCMFIDRegisterSchema):
    """Register or update a Firebase Installation ID for the current user."""
    validate_fid(payload.fid)

    device, _ = FCMDevice.objects.update_or_create(
        fid=payload.fid,
        defaults={"user": request.user, "active": True},
    )

    return Status(201, device)


@router.delete("/fcm/unregister/{path:fid}", response={204: None}, url_name="unregister_fcm_fid")
def unregister_fcm_fid(request: HttpRequest, fid: str):
    """Delete an installation registered to the current user."""
    FCMDevice.objects.filter(fid=fid, user=request.user).delete()
    return Status(204, None)
