from enum import Enum

from ninja import ModelSchema

from .models import User


class ProfileAvatarTypeEnum(str, Enum):
    TIEDYE = "TD"
    IMAGE = "IM"


class UserSchema(ModelSchema):
    profile_avatar_type: ProfileAvatarTypeEnum

    @staticmethod
    def resolve_profile_image(obj: User):
        if obj.profile_image:
            return obj.profile_image.url
        return None

    class Meta:
        model = User
        fields = ["name", "profile_avatar_seed", "profile_image", "profile_avatar_type"]
