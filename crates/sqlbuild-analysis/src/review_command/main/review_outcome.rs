//! The status and exit code of a review.

use crate::review_command::_helpers::outcome::outcome;
use crate::review_command::models::ReviewReport;

/// `(status, exit code)`: `failed` 3, `findings` 1, `incomplete` 2, `passed` or `planned` 0.
#[must_use]
pub fn review_outcome(report: &ReviewReport) -> (&'static str, i32) {
    outcome(report)
}
