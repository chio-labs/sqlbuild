"""Report dbt runtime progress."""

from collections.abc import Callable

from sqlbuild.integrations.dbt.helpers.runtime.progress import report_progress as _report


def report_progress(*, on_progress: Callable[[str], None] | None, message: str) -> None:
    """Report a dbt runtime progress message when configured."""

    _ = _report(on_progress=on_progress, message=message)
