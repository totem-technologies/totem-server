from ninja import Schema


class LivekitTokenResponseSchema(Schema):
    token: str


class LivekitMuteParticipantSchema(Schema):
    order: list[str]
