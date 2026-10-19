//! The warning of an incremental model whose existing table keeps an outdated physical layout.

use serde_json::Value;

use crate::planner_strategy::constants::{
    METADATA_CONFIG_MEMBER, PHYSICAL_LAYOUT_CONFIG_KEYS, PHYSICAL_LAYOUT_PENDING_WARNING_CODE,
};
use crate::planner_strategy::models::{MaterializationType, WarningRow, WarningSeverity};

/// The warning of changed layout keys on an incremental table the plan does not recreate.
pub fn physical_layout_warning(
    model_name: &str,
    (materialization, table_recreated): (MaterializationType, bool),
    (previous_metadata_json, current_metadata_json): (Option<&str>, Option<&str>),
) -> Option<WarningRow> {
    if materialization != MaterializationType::Incremental || table_recreated {
        return None;
    }
    let previous: Value = config(previous_metadata_json?)?;
    let current: Value = config(current_metadata_json?)?;
    let changed: Vec<&str> = PHYSICAL_LAYOUT_CONFIG_KEYS
        .into_iter()
        .filter(|key| layout_value(&previous, key) != layout_value(&current, key))
        .collect();
    if changed.is_empty() {
        return None;
    }
    Some(WarningRow {
        severity: WarningSeverity::Warning,
        message: format!(
            "{model_name}: {} changed, but the existing table keeps its old physical layout; \
             a full refresh (`sqb build {model_name} --full-refresh`) rebuilds it with the new \
             layout",
            changed.join(", ")
        ),
        code: Some(PHYSICAL_LAYOUT_PENDING_WARNING_CODE),
    })
}

/// The recorded config, or none for metadata that is not a JSON object with one.
fn config(metadata_json: &str) -> Option<Value> {
    match serde_json::from_str::<Value>(metadata_json) {
        Ok(mut metadata) => Some(metadata.get_mut(METADATA_CONFIG_MEMBER)?.take()),
        Err(_) => None,
    }
}

/// A key's value, with an absent key read as null.
fn layout_value<'a>(config: &'a Value, key: &str) -> &'a Value {
    config.get(key).unwrap_or(&Value::Null)
}
