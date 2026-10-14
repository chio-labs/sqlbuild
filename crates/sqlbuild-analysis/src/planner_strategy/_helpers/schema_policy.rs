//! The effective `on_schema_change` policy.

use crate::planner_strategy::constants::APPEND_NEW_COLUMNS;

/// `on_schema_change or append_new_columns`.
pub(crate) fn effective_on_schema_change(on_schema_change: Option<&str>) -> &str {
    match on_schema_change {
        Some(value) if !value.is_empty() => value,
        _ => APPEND_NEW_COLUMNS,
    }
}
