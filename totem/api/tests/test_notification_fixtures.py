import json
from pathlib import Path

from totem.notifications.schemas import NotificationType, SessionNotificationPayload

FIXTURE = Path(__file__).parent / "fixtures" / "session_notification_payloads.json"


def test_notification_fixture_matches_schema() -> None:
    expected = [
        SessionNotificationPayload(type=kind, space_slug="example-space", session_slug="example-session").model_dump(
            mode="json", exclude_none=True
        )
        for kind in NotificationType
    ]
    assert json.loads(FIXTURE.read_text()) == expected
