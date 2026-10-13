//! Persisted runs newest first.

use std::cmp::Reverse;

use crate::cost_report::_helpers::instants::utc_micros;
use crate::cost_report::models::CostRun;

/// The runs by completion instant, then run ID, both descending.
#[must_use]
pub fn order_cost_runs(mut runs: Vec<CostRun>) -> Vec<CostRun> {
    runs.sort_by_cached_key(|run| {
        Reverse((
            utc_micros(&run.completed_at).unwrap_or(i128::MIN),
            run.run_id.clone(),
        ))
    });
    runs
}
