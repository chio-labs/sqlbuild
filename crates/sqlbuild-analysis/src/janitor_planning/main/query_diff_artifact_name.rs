//! The reserved relation name of one run's query-diff artifact.

use crate::janitor_planning::constants::QUERY_DIFF_ARTIFACT_PREFIX;

/// The artifact relation name for `run_id` and `side`, which `query_diff_artifact_parts` parses.
#[must_use]
pub fn query_diff_artifact_name(run_id: &str, side: &str) -> String {
    format!("{QUERY_DIFF_ARTIFACT_PREFIX}{run_id}_{side}")
}
