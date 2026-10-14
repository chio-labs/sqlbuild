//! Schema actions resolved from a model's schema findings and `on_schema_change`.

use crate::planner_changes::models::{SchemaChangeKind, SchemaFindingRow};
use crate::planner_strategy::_helpers::schema_policy::effective_on_schema_change;
use crate::planner_strategy::constants::{APPEND_NEW_COLUMNS, SYNC_ALL_COLUMNS};
use crate::planner_strategy::models::{SchemaActionKind, SchemaActionRow};

/// Added columns under `append_new_columns`; added, removed and retyped columns under `sync_all_columns`.
pub fn schema_actions(
    findings: &[SchemaFindingRow],
    on_schema_change: Option<&str>,
) -> Vec<SchemaActionRow> {
    let effective: &str = effective_on_schema_change(on_schema_change);
    let sync: bool = effective == SYNC_ALL_COLUMNS;
    if !sync && effective != APPEND_NEW_COLUMNS {
        return Vec::new();
    }
    findings
        .iter()
        .filter_map(|finding| {
            let (kind, column_type) = match finding.kind {
                SchemaChangeKind::ColumnAdded => {
                    (SchemaActionKind::AddColumn, finding.expected_type.clone())
                }
                SchemaChangeKind::ColumnRemoved if sync => (SchemaActionKind::DropColumn, None),
                SchemaChangeKind::ColumnTypeChanged if sync => (
                    SchemaActionKind::AlterColumnType,
                    finding.expected_type.clone(),
                ),
                SchemaChangeKind::ColumnRemoved | SchemaChangeKind::ColumnTypeChanged => {
                    return None;
                }
            };
            Some(SchemaActionRow {
                kind,
                column_name: finding.column_name.clone(),
                column_type,
            })
        })
        .collect()
}
