"""The shared facts of a per-item timeout message."""

from __future__ import annotations

from sqlbuild.runtime.execution_limits.constants import (
    CANCELLATION_TEXT,
    REPORTED_QUERY_ID_LIMIT,
)
from sqlbuild.runtime.execution_limits.models import ItemTimeoutReport


def timeout_report_lines(*, report: ItemTimeoutReport, label: str) -> list[str]:
    """The headline, then indented limit source, cancellation outcome and query ID lines."""

    cancellation: str = CANCELLATION_TEXT[report.cancellation]
    if report.cancellation_detail:
        cancellation = f"{cancellation} ({report.cancellation_detail})"
    lines: list[str] = [
        f"{label} '{report.name}' timed out after {report.elapsed_seconds:.1f}s "
        f"(limit {report.limit}).",
        f"  Limit set by:  {report.source}",
        f"  Cancellation:  {cancellation}",
    ]
    if report.query_ids:
        shown: tuple[str, ...] = report.query_ids[-REPORTED_QUERY_ID_LIMIT:]
        omitted: int = len(report.query_ids) - len(shown)
        suffix: str = f" (+{omitted} earlier)" if omitted else ""
        lines.append(f"  Query IDs:     {', '.join(shown)}{suffix}")
    return lines
