from unittest.mock import MagicMock, patch

import pytest

from totem.utils.management.commands import totem_tasks


def test_run_tasks_continues_after_failure():
    error = RuntimeError("boom")
    failing = MagicMock(side_effect=error)
    after = MagicMock()
    with (
        patch.object(totem_tasks, "space_tasks", [failing, after]),
        patch.object(totem_tasks, "email_tasks", []),
        patch.object(totem_tasks, "notification_tasks", []),
        patch.object(totem_tasks, "user_tasks", []),
        patch.object(totem_tasks, "room_tasks", []),
        patch.object(totem_tasks.sentry_sdk, "capture_exception") as capture,
        pytest.raises(totem_tasks.TasksFailed),
    ):
        totem_tasks.run_tasks_impl()
    after.assert_called_once()
    capture.assert_called_once_with(error)
