//! The left-column resource type of an execution progress row.

use crate::plan_display::constants::{CUSTOM, SNAPSHOT, TABLE, VIEW};
use crate::plan_display::models::ModelLabelFacts;

/// `view`, `custom` or `snapshot` for those materializations, otherwise `table`.
#[must_use]
pub fn model_resource_type(entry: Option<&ModelLabelFacts>) -> &'static str {
    let Some(entry) = entry else {
        return TABLE;
    };
    [VIEW, CUSTOM, SNAPSHOT]
        .into_iter()
        .find(|kind| entry.materialization_type == *kind)
        .unwrap_or(TABLE)
}
