from typing import Optional

import jwt
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router
from ninja.security import HttpBearer

from totem.users.models import User
from totem.users.schemas import UserSchema


class JWTAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> Optional[User]:
        try:
            # Decode JWT token
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

            # Extract user_id and device_id
            api_key = payload.get("api_key")
            exp = payload.get("exp")

            # Check if token is expired
            if not exp or timezone.now().timestamp() > exp:
                return None

            # Get user
            try:
                user = User.objects.get(api_key=api_key)

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


@router.get("/currentuser", response={200: UserSchema}, url_name="current_user")
def current_user(request: HttpRequest):
    return request.user
