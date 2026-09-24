"""Local helpers for CLI entry tests."""

from __future__ import annotations

from sqlbuild.runtime.event_exporting.models import (
    EventExporterAccounting,
    EventExporterCounts,
    EventExportSummary,
)


def build_export_summary(counts: tuple[tuple[str, int, int, int, int], ...]) -> EventExportSummary:
    per_exporter: tuple[EventExporterAccounting, ...] = tuple(
        EventExporterAccounting(
            exporter_name=name,
            counts=EventExporterCounts(
                accepted=accepted, delivered=delivered, failed=failed, dropped=dropped
            ),
        )
        for name, accepted, delivered, failed, dropped in counts
    )
    return EventExportSummary(
        aggregate=EventExporterCounts(
            accepted=sum(item.counts.accepted for item in per_exporter),
            delivered=sum(item.counts.delivered for item in per_exporter),
            failed=sum(item.counts.failed for item in per_exporter),
            dropped=sum(item.counts.dropped for item in per_exporter),
        ),
        per_exporter=per_exporter,
        queue_depth=0,
        queue_capacity=1024,
        flush_complete=all(item.counts.dropped == 0 for item in per_exporter),
    )
