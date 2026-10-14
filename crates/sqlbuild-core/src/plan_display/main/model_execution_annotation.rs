//! The annotation an execution progress row shows after the model name.

use crate::plan_display::_helpers::labels::snapshot_label;
use crate::plan_display::constants::{INCREMENTAL, INCREMENTAL_ACTIONS, SNAPSHOT};
use crate::plan_display::models::ModelLabelFacts;

/// The snapshot details, or the incremental strategy of an incremental model.
#[must_use]
pub fn model_execution_annotation(entry: Option<&ModelLabelFacts>) -> String {
    let Some(entry) = entry else {
        return String::new();
    };
    if entry.materialization_type == SNAPSHOT {
        return snapshot_label(entry, false);
    }
    let incremental: bool = INCREMENTAL_ACTIONS.contains(&entry.action.as_str())
        || entry.materialization_type == INCREMENTAL;
    if !incremental {
        return String::new();
    }
    entry.incremental_strategy.clone().unwrap_or_default()
}
