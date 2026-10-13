//! Whether a diff found differences, and the resulting outcome.

use crate::diff_report::constants::{FINDINGS_OUTCOME, PASS_OUTCOME};
use crate::diff_report::models::DiffModelFacts;

pub(crate) fn has_schema_differences(model: &DiffModelFacts) -> bool {
    !(model.added_columns.is_empty()
        && model.removed_columns.is_empty()
        && model.type_changes.is_empty())
}

/// Whether any model has schema or row differences.
pub(crate) fn has_findings(models: &[DiffModelFacts]) -> bool {
    models.iter().any(|model| {
        has_schema_differences(model)
            || model.rows.as_ref().is_some_and(|rows| {
                rows.unequal_count != 0 || rows.left_only_count != 0 || rows.right_only_count != 0
            })
    })
}

/// The explicit outcome, or `findings`/`pass` from the results.
pub(crate) fn resolved_outcome(models: &[DiffModelFacts], outcome: Option<&str>) -> String {
    outcome
        .filter(|outcome| !outcome.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| {
            if has_findings(models) {
                FINDINGS_OUTCOME
            } else {
                PASS_OUTCOME
            }
            .to_owned()
        })
}
