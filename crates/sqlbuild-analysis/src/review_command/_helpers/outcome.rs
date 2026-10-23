//! The status and exit code a report's evidence decides.

use crate::review_command::constants::{
    FAILED_NODE, FAILED_STATUS, FAILURE_EXIT_CODE, FINDINGS_EXIT_CODE, FINDINGS_STATUS,
    INCOMPLETE_EXIT_CODE, INCOMPLETE_STATUS, PASS_EXIT_CODE, PASSED_STATUS, PLANNED_STATUS,
};
use crate::review_command::models::ReviewReport;

/// Whether the run failed: an error, a failed build, or a review schema it could not drop.
pub(crate) fn failed(report: &ReviewReport) -> bool {
    report.error.is_some()
        || report.nodes.iter().any(|node| node.status == FAILED_NODE)
        || report
            .schema
            .as_ref()
            .is_some_and(|schema| schema.created && !schema.dropped)
}

/// `(status, exit code)`: failure wins over findings, findings over incomplete coverage.
pub(crate) fn outcome(report: &ReviewReport) -> (&'static str, i32) {
    if failed(report) {
        return (FAILED_STATUS, FAILURE_EXIT_CODE);
    }
    if report.dry_run {
        return (PLANNED_STATUS, PASS_EXIT_CODE);
    }
    if !report.findings.is_empty() {
        return (FINDINGS_STATUS, FINDINGS_EXIT_CODE);
    }
    if !report.incomplete.is_empty() {
        return (INCOMPLETE_STATUS, INCOMPLETE_EXIT_CODE);
    }
    (PASSED_STATUS, PASS_EXIT_CODE)
}
