//! The single live row naming every running item.

use crate::cli_text::models::CliStyle;
use crate::nested_progress::constants::{CLEAR_LINE, LABEL_WIDTH, LIVE_ROW_PADDING};
use crate::nested_progress::models::NestedLayout;

/// The running item, or a count and list of running items, cut to the terminal.
#[must_use]
pub fn render_nested_spinner_line(
    running: &[String],
    frame: &str,
    layout: &NestedLayout,
    style: CliStyle,
) -> String {
    let text: String = match running {
        [only] => only.clone(),
        _ => format!("{} running: {}", running.len(), running.join(", ")),
    };
    let available: i64 = layout.columns as i64 - (LABEL_WIDTH + LIVE_ROW_PADDING) as i64;
    let width: usize = (layout.name_width as i64).min(available).max(1) as usize;
    let name: String = if text.chars().count() <= width {
        text
    } else {
        format!(
            "{}...",
            text.chars()
                .take(width.saturating_sub(3))
                .collect::<String>()
        )
    };
    format!(
        "{CLEAR_LINE}    {:<LABEL_WIDTH$}{name:<width$} {}",
        layout.label,
        style.status(frame)
    )
}
