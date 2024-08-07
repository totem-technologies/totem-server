from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.security import APIKeyHeader

from totem.circles.api import router as circles_router
from totem.users.models import User
from totem.users.schemas import UserSchema

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
