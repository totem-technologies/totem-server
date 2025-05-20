import uuid
from typing import Optional

from django.http import HttpRequest
from ninja import File, Router
from ninja.errors import ValidationError
from ninja.files import UploadedFile

from totem.api.mobile_api import JWTAuth  # Assuming JWTAuth is accessible here
from totem.email.utils import validate_email_blocked
from totem.users.models import User
from totem.users.schemas import UserSchema, UserUpdateSchema

user_router = Router(auth=JWTAuth())


@user_router.get("/current", response={200: UserSchema}, url_name="mobile_user_current")
def get_current_user(request: HttpRequest):
    return request.user


@user_router.patch("/update", response={200: UserSchema}, url_name="mobile_user_update")
def update_current_user(
    request: HttpRequest,
    payload: UserUpdateSchema,
    profile_image: Optional[UploadedFile] = File(...),
):
    user: User = request.user
    update_fields = []

    if payload.name is not None:
        user.name = payload.name
        update_fields.append("name")

    if payload.email is not None:
        # Validate email format and if it's blocked
        validate_email_blocked(payload.email)
        # Check if email is already in use by another user
        if User.objects.exclude(pk=user.pk).filter(email__iexact=payload.email).exists():
            raise ValidationError([{"email": "Sorry, but your email address is not allowed."}])
        user.email = payload.email
        update_fields.append("email")

    if payload.timezone is not None:
        user.timezone = payload.timezone
        update_fields.append("timezone")

    if payload.newsletter_consent is not None:
        user.newsletter_consent = payload.newsletter_consent
        update_fields.append("newsletter_consent")

    if payload.profile_avatar_type is not None:
        user.profile_avatar_type = payload.profile_avatar_type.value
        update_fields.append("profile_avatar_type")

    if payload.randomize_avatar_seed:
        user.profile_avatar_seed = uuid.uuid4()
        update_fields.append("profile_avatar_seed")

    if profile_image:
        if profile_image.size > 5 * 1024 * 1024:  # 5MB limit
            raise ValidationError([{"profile_image": "Image too large. Max 5MB."}])
        user.profile_image = profile_image
        # If user had a tie-dye avatar, switch to image
        if user.profile_avatar_type == User.ProfileChoices.TIEDYE:
            user.profile_avatar_type = User.ProfileChoices.IMAGE
        update_fields.append("profile_image")
        update_fields.append("profile_avatar_type")  # Ensure this is saved if changed

    if update_fields:
        # Clean is called by save if update_fields is not specified.
        # Since we are specifying update_fields, we should call clean manually.
        user.full_clean(exclude=list(set(User._meta.fields_map.keys()) - set(update_fields)))
        user.save(update_fields=update_fields)

    return user
