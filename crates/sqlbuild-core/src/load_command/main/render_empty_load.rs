//! The output of a load with nothing selected.

use crate::cli_text::models::CliStyle;
use crate::load_command::main::render_load_footer::render_load_footer;
use crate::load_command::models::LoadCounts;

/// A note that no managed sources were selected, then a zero-count completion line.
#[must_use]
pub fn render_empty_load(style: CliStyle) -> String {
    format!(
        "{}\n{}",
        style.muted("  No managed sources selected."),
        render_load_footer(&[], (LoadCounts::default(), 0.0), style)
    )
}
