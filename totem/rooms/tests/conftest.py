from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def admission_notification_transport() -> Iterator[MagicMock]:
    """Domain tests never publish to the configured LiveKit deployment."""
    with patch("totem.rooms.admission.services.publish_admission_changed", return_value=True) as publish:
        yield publish
