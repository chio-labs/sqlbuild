//! Account undelivered exporter attempts as dropped.

use crate::event_export::models::ExporterCounts;

/// The counts with one dropped attempt for each exporter index in `indices`.
#[must_use]
pub fn drop_lifecycle_attempts(
    mut counts: Vec<ExporterCounts>,
    indices: &[usize],
) -> Vec<ExporterCounts> {
    for index in indices {
        if let Some(counts) = counts.get_mut(*index) {
            counts.dropped += 1;
        }
    }
    counts
}
