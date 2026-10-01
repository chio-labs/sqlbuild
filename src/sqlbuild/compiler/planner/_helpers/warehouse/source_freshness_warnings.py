"""Plan warnings that explain why source freshness could not be observed."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import PlanWarning
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
    SourceFreshnessUnknown,
)

_NAME_LIMIT: int = 10


def build_source_freshness_unknown_warnings(
    *, source_freshness: DirectSourceFreshnessPlanningResult
) -> tuple[PlanWarning, ...]:
    """Return one warning per distinct reason that left source freshness unknown."""

    names_by_reason: dict[tuple[str, str], list[str]] = {}
    unknown: SourceFreshnessUnknown
    for unknown in source_freshness.unknown_sources.values():
        first_line: str = next(iter(unknown.message.strip().splitlines()), "")
        names_by_reason.setdefault((unknown.reason.value, first_line), []).append(
            unknown.source_name
        )
    return tuple(
        PlanWarning(
            model_name=None,
            severity=WarningSeverity.WARNING,
            message=(f"source freshness unknown ({reason}) for {_format_names(names)}: {message}"),
        )
        for (reason, message), names in names_by_reason.items()
    )


def _format_names(names: list[str]) -> str:
    shown: str = ", ".join(names[:_NAME_LIMIT])
    if len(names) > _NAME_LIMIT:
        return f"{shown} and {len(names) - _NAME_LIMIT} more"
    return shown
