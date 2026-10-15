//! Coloured, indented unified-diff lines for a changed model query.

use crate::cli_text::models::CliStyle;
use crate::plan_display::constants::{QUERY_DIFF_INDENT, UNIFIED_DIFF_HEADER_PREFIXES};

/// Indent each unified-diff line and colour additions, removals and headers.
#[must_use]
pub fn format_query_diff(diff_lines: &[String], style: CliStyle) -> Vec<String> {
    let mut formatted_lines: Vec<String> = Vec::with_capacity(diff_lines.len());
    for line in diff_lines {
        let formatted = format!("{QUERY_DIFF_INDENT}{line}");
        let header = UNIFIED_DIFF_HEADER_PREFIXES
            .iter()
            .any(|prefix| line.starts_with(prefix));
        formatted_lines.push(if line.starts_with('+') && !line.starts_with("+++") {
            style.success(&formatted)
        } else if line.starts_with('-') && !line.starts_with("---") {
            style.error(&formatted)
        } else if header {
            style.muted(&formatted)
        } else {
            formatted
        });
    }
    formatted_lines
}
