//! The plan warnings of one model.

use crate::planner_changes::models::SchemaChangeKind;
use crate::planner_strategy::_helpers::schema_policy::effective_on_schema_change;
use crate::planner_strategy::_helpers::warnings::{finding_warning, forward_only_warning, warning};
use crate::planner_strategy::constants::{
    FAIL_SCHEMA_CHANGE, IGNORE_SCHEMA_CHANGE, RECORDED_RELATION_MISSING_WARNING_CODE,
};
use crate::planner_strategy::models::{ChangeFacts, WarningInputs, WarningRow, WarningSeverity};

/// Python's `build_model_warnings`, in its order.
pub fn model_warnings(inputs: &WarningInputs, change: &ChangeFacts) -> Vec<WarningRow> {
    let effective: &str = effective_on_schema_change(inputs.on_schema_change.as_deref());
    let mut warnings: Vec<WarningRow> = Vec::new();
    if change.recorded_build_relation_missing {
        warnings.push(WarningRow {
            severity: WarningSeverity::Warning,
            message: format!(
                "{}: SQLBuild state records a previous build, but the relation no longer exists \
                 in the warehouse. It may have been dropped outside SQLBuild; planning a first \
                 run to recreate it.",
                inputs.model_name
            ),
            code: Some(RECORDED_RELATION_MISSING_WARNING_CODE),
        });
    }
    if effective == FAIL_SCHEMA_CHANGE && !change.schema_findings.is_empty() {
        warnings.push(warning(
            WarningSeverity::Error,
            "schema change detected and on_schema_change is set to fail".to_owned(),
        ));
    }
    warnings.extend(
        change
            .schema_findings
            .iter()
            .filter_map(|finding| finding_warning(finding, inputs.type_enforcement)),
    );
    warnings.extend(forward_only_warning(inputs, change));
    let backfill_findings: bool = change.schema_findings.iter().any(|finding| {
        matches!(
            finding.kind,
            SchemaChangeKind::ColumnAdded | SchemaChangeKind::ColumnTypeChanged
        )
    });
    if backfill_findings && !inputs.has_schema_actions && effective == IGNORE_SCHEMA_CHANGE {
        warnings.push(warning(
            WarningSeverity::Info,
            "schema change detected but on_schema_change is set to ignore".to_owned(),
        ));
    }
    warnings
}
