//! The close of an `--as` preview with an unambiguous nothing-changed state.

use crate::cli_text::models::CliStyle;
use crate::janitor_text::_helpers::counts::connection_label;

/// `Previewed janitor ... Nothing was changed.` and how to apply it.
#[must_use]
pub fn janitor_preview_complete_text(
    as_target: &str,
    active_target: Option<&str>,
    style: CliStyle,
) -> String {
    format!(
        "{}\nRerun with `--target {as_target}` instead of `--as {as_target}` to apply it.\n",
        style.success(&format!(
            "Previewed janitor as target '{as_target}' through {}. Nothing was changed.",
            connection_label(active_target)
        ))
    )
}
