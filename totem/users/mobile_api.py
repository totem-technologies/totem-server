import pytz
from auditlog.context import disable_auditlog
from auditlog.models import LogEntry
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import File, Router
from ninja.errors import ValidationError
from ninja.files import UploadedFile
from pytz.exceptions import UnknownTimeZoneError

from totem.email.utils import validate_email_blocked
from totem.users.models import KeeperProfile, User
from totem.users.schemas import KeeperProfileSchema, PublicUserSchema, UserSchema, UserUpdateSchema

user_router = Router()


@user_router.get("/current", response={200: UserSchema}, url_name="user_current")
def get_current_user(request: HttpRequest):
    return request.user


@user_router.get("/profile/{user_slug}", response={200: PublicUserSchema}, url_name="user_profile")
def get_user_profile(request: HttpRequest, user_slug: str):
    user = get_object_or_404(User, slug=user_slug)
    return user


@user_router.post("/update", response={200: UserSchema}, url_name="user_update")
def update_current_user(
    request: HttpRequest,
    payload: UserUpdateSchema,
):
    user: User = request.user  # type: ignore

    if payload.name is not None:
        user.name = payload.name

    if payload.email is not None:
        # Validate email format and if it's blocked
        validate_email_blocked(payload.email)
        # Check if email is already in use by another user
        if User.objects.exclude(pk=user.pk).filter(email__iexact=payload.email).exists():
            raise ValidationError([{"email": "Sorry, but this email address is not allowed."}])
        user.email = payload.email

    if payload.timezone is not None:
        try:
            user.timezone = pytz.timezone(payload.timezone)
        except UnknownTimeZoneError:
            raise ValidationError(
                [
                    {
                        "timezone": "Invalid timezone. Please provide a valid timezone (e.g., 'America/New_York', 'Europe/London')."
                    }
                ]
            )

    if payload.newsletter_consent is not None:
        user.newsletter_consent = payload.newsletter_consent

    if payload.profile_avatar_type is not None:
        user.profile_avatar_type = payload.profile_avatar_type.value

    if payload.profile_avatar_seed:
        user.profile_avatar_seed = payload.profile_avatar_seed

    user.full_clean()
    user.save()

    return user


@user_router.post("/update_image", response={200: bool}, url_name="user_update_image")
def update_current_user_image(
    request: HttpRequest,
    profile_image: UploadedFile = File(...),  # type: ignore
):
    user: User = request.user  # type: ignore
    if profile_image.size is not None and profile_image.size > 5 * 1024 * 1024:  # 5MB limit
        raise ValidationError([{"profile_image": "Image too large. Max 5MB."}])
    user.profile_image.save(profile_image.name, profile_image)
    # If user had a tie-dye avatar, switch to image
    if user.profile_avatar_type == User.ProfileChoices.TIEDYE:
        user.profile_avatar_type = User.ProfileChoices.IMAGE
    user.full_clean()
    user.save(update_fields=["profile_image", "profile_avatar_type"])  # Ensure this is saved if changed

    return True


@user_router.delete("/delete", response={200: bool}, url_name="user_delete")
def delete_current_user(request: HttpRequest):
    user: User = request.user  # type: ignore
    # make a log entry for the deletion
    LogEntry.objects.log_create(user, force_log=True, action=LogEntry.Action.DELETE).save()  # type: ignore
    with disable_auditlog():
        user.delete()
    return True


@user_router.get("/keeper/{username}", response={200: KeeperProfileSchema}, url_name="user_keeper_profile")
def keeper(request: HttpRequest, username: str):
    return get_object_or_404(KeeperProfile, username=username)
