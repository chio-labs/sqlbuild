//! A fixed-width status cell.

use crate::cli_text::_helpers::layout::status_cell;
use crate::cli_text::models::CliStyle;

/// The styled status padded on its plain width.
#[must_use]
pub fn format_status_cell(style: CliStyle, status: &str, width: usize) -> String {
    status_cell(style, status, width)
}
