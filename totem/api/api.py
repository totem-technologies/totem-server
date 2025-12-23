import os

from django.http import HttpRequest
from ninja import File, NinjaAPI, Router, Schema
from ninja.files import UploadedFile

from totem.circles.api import router as circles_router
from totem.users.models import User
from totem.users.schemas import ProfileAvatarTypeEnum, PublicUserSchema

from .auth import router as auth_router
from .mobile_api import router as mobile_router

api = NinjaAPI(title="Totem API", version="1")
dev_api = Router()
api.add_router("/dev/", dev_api)
api.add_router("/spaces/", circles_router)
mobile_api = NinjaAPI(title="Totem Mobile API", version="1", urls_namespace="mobile-api")
mobile_api.add_router("/protected/", mobile_router)
mobile_api.add_router("/auth/", auth_router)


class InvalidToken(Exception):
    pass


class Message(Schema):
    message: str


@api.get("/auth/currentuser", response={200: PublicUserSchema, 404: Message})
def current_user(request: HttpRequest):
    if request.user.is_authenticated:
        return request.user
    return 404, {"message": "Not found"}


class AvatarUpdate(Schema):
    avatar_type: ProfileAvatarTypeEnum | None
    update_avatar_seed: bool | None


@api.post("/user/avatarupdate", response={200: None, 404: Message}, url_name="user_avatar_update")
def user_avatar_update(request: HttpRequest, avatar_data: AvatarUpdate):
    if not request.user.is_authenticated:
        return 404, {"message": "Not found"}
    user: User = request.user  # type: ignore
    if avatar_data.avatar_type:
        user.profile_avatar_type = avatar_data.avatar_type
    if avatar_data.update_avatar_seed:
        user.randomize_avatar()
    user.save()
    return None


@api.post("/user/avatarimage", response={200: None, 404: Message}, url_name="user_upload_profile_image")
def user_upload_profile_image(request, file: UploadedFile = File(...)):  # type: ignore
    if not request.user.is_authenticated:
        return 404, {"message": "Not found"}
    user: User = request.user  # type: ignore
    user.profile_image.save(file.name, file)
    user.save()
    return None


@dev_api.get("/version", response={200: str}, url_name="dev_version")
def dev_version(request):
    # returns GIT_REV environment variable, if present
    return os.environ.get("GIT_REV", "unknown")
