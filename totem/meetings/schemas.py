from ninja import Schema


class LivekitTokenResponseSchema(Schema):
    token: str


class LivekitOrderSchema(Schema):
    order: list[str]


class ErrorResponseSchema(Schema):
    error: str
