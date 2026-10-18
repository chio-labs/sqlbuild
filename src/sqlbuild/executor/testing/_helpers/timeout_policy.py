"""The time limit one SQL unit test runs under."""

from __future__ import annotations

from sqlbuild._native import SqlTestPlanEntry
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy, RunItemTimeouts


def sql_test_timeout(
    *, entry: SqlTestPlanEntry, timeouts: RunItemTimeouts | None
) -> ItemTimeoutPolicy | None:
    """The CLI limit, else the test's TEST() timeout, else the target's or project's."""

    location: str = entry.source_path.as_posix() if entry.source_path else entry.name
    return (timeouts or RunItemTimeouts()).resolve(
        declared=entry.timeout,
        declared_seconds=entry.timeout_seconds,
        declared_source=f"TEST() timeout in {location}",
    )
