//! The live spinner row of the running build node.

use crate::build_progress::_helpers::text::{counter_text, head, pad, truncate_name};
use crate::build_progress::constants::{MIN_NAME_WIDTH, SPINNER_FRAMES, TYPE_WIDTH};
use crate::build_progress::models::{ProgressLayout, SpinnerRow};
use crate::cli_text::models::CliStyle;

/// The cleared line with the position, kind, name, message and spinner frame `frame`.
#[must_use]
pub fn render_build_spinner_line(
    row: &SpinnerRow,
    frame: usize,
    layout: ProgressLayout,
    style: CliStyle,
) -> String {
    let mut name: String = truncate_name(&row.name, layout.name_width);
    if !row.message.is_empty() {
        name = format!("{name}  {}", row.message);
    }
    let mut plain: String = format!(
        "  {}  {}{} ",
        counter_text(row.position, layout.total),
        pad(&row.resource_kind, TYPE_WIDTH),
        pad(&name, layout.name_width)
    );
    let max_width: i64 = (layout.columns as i64 - 2).max(MIN_NAME_WIDTH as i64);
    if plain.chars().count() as i64 > max_width {
        plain = format!("{}... ", head(&plain, (max_width - 4).max(0) as usize));
    }
    let spinner: &str = SPINNER_FRAMES[frame % SPINNER_FRAMES.len()];
    format!("\r\x1b[K{plain}{}", style.status(spinner))
}
