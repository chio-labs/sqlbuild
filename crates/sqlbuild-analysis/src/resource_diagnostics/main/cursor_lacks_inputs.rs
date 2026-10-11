//! P011: a cursor-based incremental model that reads no input to bound its cursor window.

use crate::resource_diagnostics::constants::{
    CURSOR_HELP, INCREMENTAL, RELATION_KINDS, ROLLING_WINDOW,
};
use crate::resource_diagnostics::models::CursorModel;

/// The P011 message and help for `name`, when its cursor window has no input to read.
#[must_use]
pub fn cursor_lacks_inputs(name: &str, model: &CursorModel<'_>) -> Option<(String, &'static str)> {
    let lacks: bool = model.materialized == Some(INCREMENTAL)
        && model.cursor.is_some()
        && model.microbatch_strategy != Some(ROLLING_WINDOW)
        && !model.has_cursor_inputs
        && !model
            .reference_kinds
            .iter()
            .any(|kind| RELATION_KINDS.contains(kind));
    lacks.then(|| {
        (
            format!(
                "incremental model '{name}' reads no inputs, so builds after the first cannot \
                 work out their cursor window"
            ),
            CURSOR_HELP,
        )
    })
}
