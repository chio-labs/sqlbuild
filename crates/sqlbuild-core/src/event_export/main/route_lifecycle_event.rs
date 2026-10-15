//! Filter one event across bound sinks before it is queued.

use crate::event_export::main::severity_at_least::severity_at_least;
use crate::event_export::models::{ExportPolicy, ExporterCounts, ExporterFilter};

/// The counts with each sink accepted or filtered, and the indices of sinks accepting `policy`.
#[must_use]
pub fn route_lifecycle_event(
    policy: &ExportPolicy,
    filters: &[ExporterFilter],
    mut counts: Vec<ExporterCounts>,
) -> (Vec<ExporterCounts>, Vec<usize>) {
    let mut eligible: Vec<usize> = Vec::new();
    for (index, (filter, counts)) in filters.iter().zip(counts.iter_mut()).enumerate() {
        if filter.event_kinds.contains(&policy.kind)
            && severity_at_least(policy.severity, filter.min_severity)
        {
            counts.accepted += 1;
            eligible.push(index);
        } else {
            counts.filtered += 1;
        }
    }
    (counts, eligible)
}
