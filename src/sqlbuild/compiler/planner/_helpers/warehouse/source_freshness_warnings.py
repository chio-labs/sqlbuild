"""Plan warnings that explain why source freshness could not be observed."""

from __future__ import annotations

from sqlbuild.compiler.planner.constants import SOURCE_FRESHNESS_UNKNOWN_WARNING_TITLE
from sqlbuild.compiler.planner.models import PlanWarning
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
    SourceFreshnessUnknown,
)
from sqlbuild.compiler.source_freshness.types import SourceFreshnessUnknownReason

_NAME_LIMIT: int = 10
_REASON_EXPLANATIONS: dict[SourceFreshnessUnknownReason, str] = {
    SourceFreshnessUnknownReason.UNAVAILABLE: (
        "adapter freshness metadata is unavailable, for example for a view, an external table, "
        "or a table without a last-modified time"
    ),
    SourceFreshnessUnknownReason.ERROR: "the freshness observation failed",
}


def build_source_freshness_unknown_warnings(
    *, source_freshness: DirectSourceFreshnessPlanningResult
) -> tuple[PlanWarning, ...]:
    """Return one warning per reason that left configured source freshness unknown."""

    names_by_reason: dict[SourceFreshnessUnknownReason, list[str]] = {}
    unknown: SourceFreshnessUnknown
    for unknown in source_freshness.unknown_sources.values():
        if unknown.reason in _REASON_EXPLANATIONS:
            names_by_reason.setdefault(unknown.reason, []).append(unknown.source_name)
    return tuple(
        PlanWarning(
            model_name=None,
            severity=WarningSeverity.WARNING,
            message=(
                f"{SOURCE_FRESHNESS_UNKNOWN_WARNING_TITLE} ({reason.value}) for "
                f"{_format_names(names)}: {_REASON_EXPLANATIONS[reason]}; "
                "run sqb freshness for each source's details"
            ),
        )
        for reason, names in names_by_reason.items()
    )


def _format_names(names: list[str]) -> str:
    ordered: list[str] = sorted(names)
    shown: str = ", ".join(ordered[:_NAME_LIMIT])
    if len(ordered) > _NAME_LIMIT:
        return f"{shown} and {len(ordered) - _NAME_LIMIT} more"
    return shown
