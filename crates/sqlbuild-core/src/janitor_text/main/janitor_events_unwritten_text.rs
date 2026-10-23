//! The warning that completed janitor actions have no audit events.

use crate::cli_text::main::format_phase_line::format_phase_line;
use crate::cli_text::models::CliStyle;
use crate::janitor_text::_helpers::phases::noun;

/// `✗ Audit events not written  for 5 completed actions in analytics: <error>`.
#[must_use]
pub fn janitor_events_unwritten_text(
    (count, schemas): (usize, &[String]),
    error: &str,
    style: CliStyle,
) -> String {
    format_phase_line(
        style,
        false,
        (
            "Audit events not written",
            &format!(
                "for {} in {}: {}",
                noun(count, "completed action"),
                schemas.join(", "),
                error.lines().next().unwrap_or_default()
            ),
        ),
    )
}
