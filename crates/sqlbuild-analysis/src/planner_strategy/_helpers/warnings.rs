//! The schema-finding and forward-only replay warnings of one model.

use crate::planner_changes::models::{SchemaChangeKind, SchemaColumnSource, SchemaFindingRow};
use crate::planner_strategy::constants::QUERY_CHANGE_TRACKING_HELP;
use crate::planner_strategy::models::{
    ChangeFacts, MaterializationType, WarningInputs, WarningRow, WarningSeverity,
};

/// Python's `str()` of an optional type.
fn shown(value: Option<&String>) -> &str {
    value.map_or("None", String::as_str)
}

pub(crate) fn warning(severity: WarningSeverity, message: String) -> WarningRow {
    WarningRow {
        severity,
        message,
        code: None,
    }
}

/// The warning of one schema finding, if it has one.
pub(crate) fn finding_warning(
    finding: &SchemaFindingRow,
    type_enforcement: bool,
) -> Option<WarningRow> {
    let name: &str = &finding.column_name;
    let expected: &str = shown(finding.expected_type.as_ref());
    let actual: &str = shown(finding.actual_type.as_ref());
    if type_enforcement && finding.source == SchemaColumnSource::Yml {
        return (finding.kind == SchemaChangeKind::ColumnTypeChanged).then(|| {
            warning(
                WarningSeverity::Warning,
                format!(
                    "enforced column {name} type mismatch: expected {expected}, warehouse has {actual}"
                ),
            )
        });
    }
    if finding.source != SchemaColumnSource::SqlAnalysis {
        return None;
    }
    let description: String = match finding.kind {
        SchemaChangeKind::ColumnAdded => match finding.expected_type.as_deref() {
            Some(expected) if !expected.is_empty() => {
                format!("new column not in warehouse ({expected})")
            }
            _ => "new column not in warehouse".to_owned(),
        },
        SchemaChangeKind::ColumnTypeChanged => {
            format!("expected {expected}, warehouse has {actual}")
        }
        SchemaChangeKind::ColumnRemoved => return None,
    };
    Some(warning(
        WarningSeverity::Info,
        format!("inferred column {name}: {description}"),
    ))
}

/// The forward-only replay warning of an incremental model whose definition changed.
pub(crate) fn forward_only_warning(
    inputs: &WarningInputs,
    change: &ChangeFacts,
) -> Option<WarningRow> {
    if inputs.materialization != MaterializationType::Incremental
        || !(change.query_changed || !change.changed_functions.is_empty())
        || !change.backfill_forward_only
    {
        return None;
    }
    let model_name: &str = &inputs.model_name;
    let subject: String = if change.query_changed {
        "the model's SQL changed".to_owned()
    } else {
        format!("function {} changed", change.changed_functions.join(", "))
    };
    Some(warning(
        WarningSeverity::Warning,
        format!(
            "{model_name}: {subject}, so already-built dates keep their old results - only new \
             dates will use the new query. To apply the change to existing data, choose how much \
             to reprocess: replay_on_change full (rebuild every date with the new SQL), \
             replay_on_change bounded-<duration> e.g. bounded-14d (reprocess just that window), \
             or leave it forward-only (existing dates as-is, new dates use the new query - the \
             default). If this model's output does not depend on the SQL that changed, this is \
             safe to ignore. {QUERY_CHANGE_TRACKING_HELP}"
        ),
    ))
}
