//! A single-line completion summary.

use crate::cli_text::_helpers::summary_text::completion_line;
use crate::cli_text::models::{CliStyle, CompletionState};

/// The state glyph, the label and the trailing summary.
#[must_use]
pub fn format_completion_line(
    style: CliStyle,
    state: CompletionState,
    label: &str,
    summary: Option<&str>,
) -> String {
    completion_line(style, state, label, summary)
}
