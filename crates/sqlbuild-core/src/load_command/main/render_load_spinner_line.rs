//! The live row of a running load.

use crate::cli_text::models::CliStyle;
use crate::load_command::_helpers::padding::pad_right;
use crate::load_command::constants::{KIND_WIDTH, SPINNER_FRAMES, SPINNER_NAME_WIDTH};
use crate::load_command::models::LoadSpinnerRow;

/// Carriage return, line clear, and the row with spinner frame `frame`.
#[must_use]
pub fn render_load_spinner_line(row: &LoadSpinnerRow, frame: usize, style: CliStyle) -> String {
    let name: String = if row.message.is_empty() {
        row.name.clone()
    } else {
        format!("{}  {}", row.name, row.message)
    };
    format!(
        "\r\u{1b}[K  {}/{}  {}{} {}",
        row.ordinal,
        row.total,
        pad_right(&row.resource_kind, KIND_WIDTH),
        pad_right(&name, SPINNER_NAME_WIDTH),
        style.status(SPINNER_FRAMES[frame % SPINNER_FRAMES.len()])
    )
}
