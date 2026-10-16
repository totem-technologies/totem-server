from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import KeeperProfileFactory


def relationship(
    keeper: User,
    participant: User,
    *,
    attendee: bool = True,
    joined: bool = False,
    **session_fields,
):
    if not keeper.is_keeper():
        KeeperProfileFactory(user=keeper)
    session = SessionFactory(space=SpaceFactory(author=keeper), **session_fields)
    if attendee:
        session.attendees.add(participant)
    if joined:
        session.joined.add(participant)
    return session
