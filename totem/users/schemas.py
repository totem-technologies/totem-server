from enum import Enum
from typing import Optional

from ninja import ModelSchema, Schema, Field
from pydantic import EmailStr, validator
import pytz
from pytz.exceptions import UnknownTimeZoneError

from .models import User


class ProfileAvatarTypeEnum(str, Enum):
    TIEDYE = "TD"
    IMAGE = "IM"


class PublicUserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum

    @staticmethod
    def resolve_profile_image(obj: User):
        if obj.profile_image:
            return obj.profile_image.url
        return None

    class Meta:
        model = User
        fields = ["name", "is_staff", "profile_avatar_seed", "profile_image", "profile_avatar_type"]


class UserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum

    @staticmethod
    def resolve_profile_image(obj: User):
        if obj.profile_image:
            return obj.profile_image.url
        return None

    class Meta:
        model = User
        fields = ["name", "is_staff", "api_key", "profile_avatar_seed", "profile_image", "profile_avatar_type", "email"]


# New schema for user updates
class UserUpdateSchema(Schema):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    timezone: Optional[str] = None
    newsletter_consent: Optional[bool] = None
    profile_avatar_type: Optional[ProfileAvatarTypeEnum] = None
    randomize_avatar_seed: Optional[bool] = Field(None, description="Set to true to generate a new random avatar seed.")
    # Note: profile_image will be handled as a separate File(...) parameter in the endpoint
    # to support multipart/form-data uploads.

    @validator("timezone", pre=True, always=True)
    def validate_timezone_str(cls, value: Optional[str]):
        if value is None:
            return value
        try:
            pytz.timezone(value)
            return value
        except UnknownTimeZoneError:
            raise ValueError(
                f"Invalid timezone string: '{value}'. Please provide a valid Olson timezone (e.g., 'America/New_York', 'Europe/London')."
            )
