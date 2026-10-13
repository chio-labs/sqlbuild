//! The outcome and exit code of a finished diff.

use crate::diff_report::_helpers::findings::{has_findings, has_schema_differences};
use crate::diff_report::constants::{FINDINGS_OUTCOME, INCOMPLETE_OUTCOME, PASS_OUTCOME};
use crate::diff_report::models::DiffModelFacts;

/// `pass` (0), `findings` (1), or `incomplete` (2) when a query schema blocked row comparison.
#[must_use]
pub fn diff_exit_code(models: &[DiffModelFacts], query_row_comparison: bool) -> (String, i32) {
    let incomplete: bool = query_row_comparison
        && models
            .iter()
            .any(|model| model.rows.is_none() && has_schema_differences(model));
    let (outcome, code) = if incomplete {
        (INCOMPLETE_OUTCOME, 2)
    } else if has_findings(models) {
        (FINDINGS_OUTCOME, 1)
    } else {
        (PASS_OUTCOME, 0)
    };
    (outcome.to_owned(), code)
}
