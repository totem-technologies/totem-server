from unittest.mock import MagicMock, patch

import pytest

from totem.utils.management.commands import totem_tasks


def test_run_tasks_continues_after_failure():
    error = RuntimeError("boom")
    failing = MagicMock(side_effect=error, __qualname__="failing")
    after = MagicMock()
    with (
        patch.object(totem_tasks.sentry_sdk, "capture_exception") as capture,
        pytest.raises(totem_tasks.TasksFailed, match="failing"),
    ):
        totem_tasks.run_tasks_impl([[failing, after]])
    after.assert_called_once()
    capture.assert_called_once_with(error)
