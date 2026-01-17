from enum import Enum

from ninja import Field, ModelSchema, Schema

from .models import KeeperProfile, User


class ProfileAvatarTypeEnum(str, Enum):
    TIEDYE = "TD"
    IMAGE = "IM"


class PublicUserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum
    circle_count: int | None = None

    @staticmethod
    def resolve_circle_count(obj: User) -> int:
        return obj.sessions_joined.count()

    class Meta:
        model = User
        fields = [
            "name",
            "slug",
            "is_staff",
            "profile_avatar_seed",
            "profile_image",
            "profile_avatar_type",
            "date_created",
        ]


class UserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum
    circle_count: int

    @staticmethod
    def resolve_profile_image(obj: User):
        if obj.profile_image:
            return obj.profile_image.url
        return None

    @staticmethod
    def resolve_circle_count(obj: User) -> int:
        return obj.sessions_joined.count()

    class Meta:
        model = User
        fields = [
            "name",
            "slug",
            "is_staff",
            "api_key",
            "profile_avatar_seed",
            "profile_image",
            "profile_avatar_type",
            "email",
            "date_created",
        ]


# New schema for user updates
class UserUpdateSchema(Schema):
    name: str | None = None
    email: str | None = None
    timezone: str | None = None
    newsletter_consent: bool | None = None
    profile_avatar_type: ProfileAvatarTypeEnum | None = None
    profile_avatar_seed: str | None = Field(None, description="Should be a random UUID")
    # Note: profile_image will be handled as a separate File(...) parameter in the endpoint
    # to support multipart/form-data uploads.


class KeeperProfileSchema(ModelSchema):
    user: PublicUserSchema
    circle_count: int
    month_joined: str
    bio_html: str | None = None

    @staticmethod
    def resolve_circle_count(obj: KeeperProfile) -> int:
        return obj.user.sessions_joined.count()

    @staticmethod
    def resolve_month_joined(obj: KeeperProfile) -> str:
        return obj.user.month_joined()

    @staticmethod
    def resolve_bio_html(obj: KeeperProfile) -> str | None:
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
            "bluesky_username",
        ]


class FeedbackSchema(Schema):
    message: str = Field(..., min_length=1, max_length=10000)
