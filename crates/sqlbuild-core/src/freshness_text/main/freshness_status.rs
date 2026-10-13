//! The status of an observed source.

use crate::freshness_text::models::{FreshnessStatus, StateComparison};

/// Observed without state, unknown when state is missing, else unchanged, tolerated or changed.
#[must_use]
pub fn freshness_status(comparison: StateComparison) -> FreshnessStatus {
    match comparison {
        StateComparison::NotCompared => FreshnessStatus::Observed,
        StateComparison::Missing => FreshnessStatus::Unknown,
        StateComparison::Equivalent { same_hash: true } => FreshnessStatus::Unchanged,
        StateComparison::Equivalent { same_hash: false } => FreshnessStatus::Tolerated,
        StateComparison::Different => FreshnessStatus::Changed,
    }
}
