//! The close of a janitor run whose plan changes nothing.

use crate::cli_text::main::format_completion_line::format_completion_line;
use crate::cli_text::models::{CliStyle, CompletionState};

/// `✓ Janitor completed  nothing to clean up`.
#[must_use]
pub fn janitor_nothing_to_do_text(style: CliStyle) -> String {
    format!(
        "{}\n",
        format_completion_line(
            style,
            CompletionState::Ok,
            "Janitor completed",
            Some(&style.muted("nothing to clean up"))
        )
    )
}
