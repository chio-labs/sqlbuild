//! The Snowflake table-type transition one model migration makes.

use crate::migration_values::constants::STORAGE_LABELS;

/// `origin -> stage` table types, or `None` when the stage's type is unknown.
#[must_use]
pub fn storage_transition(
    origin_is_transient: bool,
    stage_is_transient: Option<bool>,
) -> Option<String> {
    let stage: bool = stage_is_transient?;
    Some(format!(
        "{} -> {}",
        STORAGE_LABELS[usize::from(origin_is_transient)],
        STORAGE_LABELS[usize::from(stage)]
    ))
}
