from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.http import HttpRequest
from ninja import File, NinjaAPI, Schema
from ninja.files import UploadedFile
from ninja.security import APIKeyHeader

from totem.circles.api import router as circles_router
from totem.users.models import User
from totem.users.schemas import ProfileAvatarTypeEnum, UserSchema

api = NinjaAPI(title="Totem API", version="1")
api.add_router("/spaces/", circles_router)


class InvalidToken(Exception):
    pass


class Message(Schema):
    message: str


@api.exception_handler(InvalidToken)
def on_invalid_token(request, exc):
    return api.create_response(request, {"detail": "Invalid token supplied"}, status=401)


class ApiKey(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request, key):
        try:
            return User.objects.get(api_key=key)
        except User.DoesNotExist:
            pass


@api.get("/protected", auth=ApiKey())
def secret(request):
    return {"token": request.auth}


class LoginOut(Schema):
    login: bool


@api.post("/auth/login", response={200: LoginOut})
def login(request, email: str):
    # user_login(email, request, mobile=True)
    return {"login": True}


class TokenOut(Schema):
    key: str


@api.post("/auth/token", response={200: TokenOut})
def token(request, token: str):
    user = authenticate(
        request,
        sesame=token,
        scope="",
        max_age=None,
    )
    if user is None:
        raise InvalidToken
    auth_login(request, user)  # updates the last login date
    return {"key": str(user.api_key)}  # type: ignore


@api.get("/auth/currentuser", response={200: UserSchema, 404: Message})
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
