//! The announcement of an inspection-only `--as` preview.

use crate::janitor_text::_helpers::counts::connection_label;

/// `Previewing janitor as target ... (inspection only).`
#[must_use]
pub fn janitor_preview_start_text(as_target: &str, active_target: Option<&str>) -> String {
    format!(
        "Previewing janitor as target '{as_target}' through {} (inspection only).\n",
        connection_label(active_target)
    )
}
