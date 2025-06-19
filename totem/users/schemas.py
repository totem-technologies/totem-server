from enum import Enum
from typing import Optional

from ninja import Field, ModelSchema, Schema

from .models import KeeperProfile, User


class ProfileAvatarTypeEnum(str, Enum):
    TIEDYE = "TD"
    IMAGE = "IM"


class PublicUserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum
    keeper_profile_username: Optional[str] = None

    @staticmethod
    def resolve_profile_image(obj: User):
        if obj.profile_image:
            return obj.profile_image.url
        return None

    @staticmethod
    def resolve_keeper_profile_username(obj: User) -> Optional[str]:
        if obj.keeper_profile:
            return obj.keeper_profile.username
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
    email: Optional[str] = None
    timezone: Optional[str] = None
    newsletter_consent: Optional[bool] = None
    profile_avatar_type: Optional[ProfileAvatarTypeEnum] = None
    profile_avatar_seed: Optional[str] = Field(None, description="Should be a random UUID")
    # Note: profile_image will be handled as a separate File(...) parameter in the endpoint
    # to support multipart/form-data uploads.


class KeeperProfileSchema(ModelSchema):
    user: Optional[PublicUserSchema]
    circle_count: int = 0
    month_joined: str
    bio_html: Optional[str] = None

    @staticmethod
    def resolve_circle_count(obj: KeeperProfile) -> int:
        return obj.user.events_joined.count()

    @staticmethod
    def resolve_month_joined(obj: KeeperProfile) -> str:
        return obj.user.month_joined()
    
    @staticmethod
    def resolve_bio_html(obj: KeeperProfile) -> Optional[str]:
        if obj.bio:
            return obj.render_markdown(obj.bio)
        return None

    class Meta:
        model = KeeperProfile
        fields = [
            "username",
            "title",
            "bio",
            "location",
            "languages",
            "instagram_username",
            "website",
            "x_username",
            "user",
        ]
