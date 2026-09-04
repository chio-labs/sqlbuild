"""Public post-execution JSON degradation helpers."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_result_document import (
    format_degraded_execution_json as _format_degraded_execution_json,
)
from sqlbuild.cli.output._helpers.execution_result_document import (
    warn_execution_json_degraded as _warn_execution_json_degraded,
)


def degraded_execution_json(
    *, command: str, status: str, error: Exception, execution_succeeded: bool
) -> str:
    """Warn and format a minimal valid document after projection failure."""

    _ = _warn_execution_json_degraded(error=error, execution_succeeded=execution_succeeded)
    return _format_degraded_execution_json(command=command, status=status)
