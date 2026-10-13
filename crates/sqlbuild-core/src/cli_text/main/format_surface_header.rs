//! The command surface header of human CLI output.

use crate::cli_text::_helpers::layout::surface_header;
use crate::cli_text::models::CliStyle;

/// `format_surface_header`: accent title plus dim context.
#[must_use]
pub fn format_surface_header(style: CliStyle, title: &str, context: &str) -> String {
    surface_header(style, title, context)
}
