//! The live line of a transient status: a spinner frame and the current message.

use crate::cli_text::constants::ELLIPSIS;
use crate::cli_text::models::CliStyle;

/// The frame and the first message line, cut to fit `columns` (`0` leaves it uncut).
#[must_use]
pub fn format_status_spinner_line(
    frame: &str,
    message: &str,
    columns: usize,
    style: CliStyle,
) -> String {
    let text: &str = message.lines().next().unwrap_or("");
    let width: usize = columns.saturating_sub(frame.chars().count() + 2);
    let fitted: String = if columns == 0 || text.chars().count() <= width {
        text.to_owned()
    } else {
        format!(
            "{}{ELLIPSIS}",
            text.chars()
                .take(width.saturating_sub(ELLIPSIS.len()))
                .collect::<String>()
        )
    };
    format!("{} {fitted}", style.success(frame))
}
