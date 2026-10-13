//! One human check result row.

use crate::check_command::constants::{KIND_LABEL, KIND_WIDTH, NAME_WIDTH};
use crate::check_command::models::CheckRow;
use crate::cli_text::models::CliStyle;

/// Kind, padded name, status, duration and detail, then each warning on its own line.
#[must_use]
pub fn render_check_row(check: &CheckRow, style: CliStyle) -> String {
    let result = &check.result;
    let padding: String = " ".repeat(NAME_WIDTH.saturating_sub(result.name.chars().count()));
    let mut text: String = format!(
        "  {KIND_LABEL:<KIND_WIDTH$}{}{padding} {}",
        result.name,
        style.status(result.status.label())
    );
    if let Some(duration) = check.duration_ms {
        text.push_str(&format!("  {:.2}s", duration / 1000.0));
    }
    let detail: Option<&String> = result
        .error_message
        .as_ref()
        .filter(|error| !error.is_empty())
        .or(result.message.as_ref());
    if let Some(detail) = detail.filter(|detail| !detail.is_empty()) {
        text.push_str(&format!("  {detail}"));
    }
    text.push('\n');
    for warning in &result.warning_messages {
        text.push_str(&format!("    {}\n", style.warning(warning)));
    }
    text
}
