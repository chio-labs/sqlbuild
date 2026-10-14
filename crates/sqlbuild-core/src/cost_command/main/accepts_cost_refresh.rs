//! Whether refreshed cost telemetry may replace the persisted summary.

use crate::cost_command::constants::LEDGER_PERSISTENCE_FAILURE_PREFIX;
use crate::cost_command::models::CostCoverage;

fn status_rank(status: &str) -> Option<u8> {
    match status {
        "collection_failed" | "unavailable" => Some(0),
        "pending" => Some(1),
        "partial" => Some(2),
        "complete" => Some(3),
        _ => None,
    }
}

fn coverage_gain(current: &CostCoverage, candidate: &CostCoverage) -> bool {
    candidate.expected_statement_count > current.expected_statement_count
        || candidate.observed_statement_count > current.observed_statement_count
        || candidate.query_count > current.query_count
}

/// Accept only when status and coverage cannot regress; `None` for an unknown status.
#[must_use]
pub fn accepts_cost_refresh(current: &CostCoverage, candidate: &CostCoverage) -> Option<bool> {
    if status_rank(&candidate.status)? < status_rank(&current.status)? {
        return Some(false);
    }
    let ledger_failure: bool = current
        .limitations
        .iter()
        .any(|limitation| limitation.starts_with(LEDGER_PERSISTENCE_FAILURE_PREFIX));
    if ledger_failure && !coverage_gain(current, candidate) {
        return Some(false);
    }
    Some(
        candidate.expected_statement_count >= current.expected_statement_count
            && candidate.observed_statement_count >= current.observed_statement_count
            && candidate.query_count >= current.query_count,
    )
}
