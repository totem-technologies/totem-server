from datetime import datetime
from ninja import Schema


class FCMTokenRegisterSchema(Schema):
    token: str


class FCMTokenResponseSchema(Schema):
    token: str
    active: bool
    created_at: datetime
