//! Whether a raw-query diff user error means incomplete evidence rather than a failed run.

use crate::diff_report::constants::{INCOMPLETE_EXECUTION_CODES, INCOMPLETE_PREPARATION_CODES};
use crate::diff_report::types::QueryDiffPhase;

/// Input and preflight rejections are incomplete (exit 2); other failures are execution failures.
#[must_use]
pub fn is_incomplete_query_failure(phase: QueryDiffPhase, code: &str) -> bool {
    match phase {
        QueryDiffPhase::Preparation => INCOMPLETE_PREPARATION_CODES.contains(&code),
        QueryDiffPhase::Execution => INCOMPLETE_EXECUTION_CODES.contains(&code),
    }
}
