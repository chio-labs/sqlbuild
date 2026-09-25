"""Failure-detail projection over scenario step results."""

from __future__ import annotations

from sqlbuild.executor.scenario.models import ScenarioFailureDetails
from sqlbuild.executor.scheduling.types import ExecutionStatus


def first_failure_details(
    *,
    results: tuple[object, ...],
    fallback_message: str,
    fallback_code: str | None = None,
) -> ScenarioFailureDetails:
    """Return the first failed step's message plus the first failed code and help present."""

    failed: tuple[object, ...] = tuple(
        result for result in results if getattr(result, "status", None) == ExecutionStatus.FAILED
    )
    error_message: str | None = None
    if failed:
        first_message: str | None = _non_empty_text(getattr(failed[0], "error_message", None))
        error_message = first_message if first_message is not None else fallback_message
    return ScenarioFailureDetails(
        error_code=_first_text(results=failed, field_name="error_code") or fallback_code,
        error_help=_first_text(results=failed, field_name="error_help"),
        error_message=error_message,
    )


def _first_text(*, results: tuple[object, ...], field_name: str) -> str | None:
    result: object
    for result in results:
        text: str | None = _non_empty_text(getattr(result, field_name, None))
        if text is not None:
            return text
    return None


def _non_empty_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
