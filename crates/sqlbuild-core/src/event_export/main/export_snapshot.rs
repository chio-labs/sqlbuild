//! Summarise per-exporter accounting into one immutable snapshot.

use crate::event_export::models::{ExportSnapshot, ExporterCounts, SnapshotInputs};

/// The aggregate and per-exporter counts; complete only when drained and every attempt is settled.
#[must_use]
pub fn export_snapshot(inputs: SnapshotInputs<'_>) -> ExportSnapshot {
    let mut aggregate: ExporterCounts = ExporterCounts::default();
    for (_, counts) in inputs.exporters {
        aggregate.accepted += counts.accepted;
        aggregate.filtered += counts.filtered;
        aggregate.delivered += counts.delivered;
        aggregate.dropped += counts.dropped;
        aggregate.failed += counts.failed;
    }
    let flush_complete: bool = inputs.drained
        && inputs.queue_depth == 0
        && aggregate.accepted == aggregate.delivered + aggregate.failed + aggregate.dropped;
    ExportSnapshot {
        aggregate,
        per_exporter: inputs.exporters.to_vec(),
        queue_depth: inputs.queue_depth,
        queue_capacity: inputs.queue_capacity,
        flush_complete,
    }
}
