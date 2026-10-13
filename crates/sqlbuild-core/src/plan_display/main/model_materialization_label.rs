//! The materialization label of a model in plan summaries.

use crate::plan_display::_helpers::labels::snapshot_label;
use crate::plan_display::constants::{CUSTOM, INCREMENTAL, MICROBATCH_MODE, SNAPSHOT, TABLE, VIEW};
use crate::plan_display::models::ModelLabelFacts;

fn incremental_label(entry: &ModelLabelFacts) -> String {
    let strategy: &str = entry
        .incremental_strategy
        .as_deref()
        .filter(|strategy| !strategy.is_empty())
        .unwrap_or(INCREMENTAL);
    let mut parts: Vec<&str> = Vec::new();
    if let Some(cursor_type) = &entry.cursor_type {
        parts.push(cursor_type);
    }
    if entry.incremental_mode.as_deref() == Some(MICROBATCH_MODE) {
        parts.push(MICROBATCH_MODE);
    }
    if parts.is_empty() {
        return strategy.to_owned();
    }
    format!("{strategy} ({})", parts.join(", "))
}

/// `view`, `table`, the incremental strategy with its cursor details, the snapshot details or `<name> (custom)`.
#[must_use]
pub fn model_materialization_label(entry: &ModelLabelFacts) -> String {
    match entry.materialization_type.as_str() {
        VIEW | TABLE => entry.materialization_type.clone(),
        INCREMENTAL => incremental_label(entry),
        SNAPSHOT => snapshot_label(entry, true),
        CUSTOM => format!(
            "{} (custom)",
            entry
                .custom_materialization_name
                .as_deref()
                .filter(|name| !name.is_empty())
                .unwrap_or(CUSTOM)
        ),
        other => other.to_owned(),
    }
}
