from enum import Enum
from typing import Optional

from ninja import Field, ModelSchema, Schema

from .models import KeeperProfile, User


class ProfileAvatarTypeEnum(str, Enum):
    TIEDYE = "TD"
    IMAGE = "IM"


class PublicUserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum

    class Meta:
        model = User
        fields = ["name", "slug", "is_staff", "profile_avatar_seed", "profile_image", "profile_avatar_type"]


class UserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum
    sessions_joined: int
    spaces_joined: int

    @staticmethod
    def resolve_profile_image(obj: User):
        if obj.profile_image:
            return obj.profile_image.url
        return None

    @staticmethod
    def resolve_sessions_joined(obj: User):
        return obj.events_joined.count()

    @staticmethod
    def resolve_spaces_joined(obj: User):
        events = obj.events_joined.all()
        space_slugs = set(event.circle.slug for event in events if event.circle.published)
        return len(space_slugs)

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
    user: PublicUserSchema
    circle_count: int
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
        ]
