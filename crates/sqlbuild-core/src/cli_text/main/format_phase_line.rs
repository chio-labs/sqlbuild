//! The concise phase-completion line of human CLI output.

use crate::cli_text::_helpers::layout::phase_line;
use crate::cli_text::models::CliStyle;

/// `format_phase_line`: state glyph, label, dim summary.
#[must_use]
pub fn format_phase_line(style: CliStyle, ok: bool, (label, summary): (&str, &str)) -> String {
    phase_line(style, ok, label, summary)
}
