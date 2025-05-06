from enum import Enum
from ninja import Schema
from typing import Optional


class DeviceTypeEnum(str, Enum):
    IOS = "ios"
    ANDROID = "android"


class FCMTokenRegisterSchema(Schema):
    token: str
    device_id: Optional[str] = None
    device_type: DeviceTypeEnum


class FCMTokenResponseSchema(Schema):
    token: str
    device_id: Optional[str]
    device_type: str
    active: bool
    created_at: str
