//! The bold group header that starts each run of grouped rows.

use crate::cli_text::models::CliStyle;

/// The header line, after a blank line unless it is the first group.
#[must_use]
pub fn render_group_header(group_name: &str, first: bool, style: CliStyle) -> String {
    let prefix: &str = if first { "" } else { "\n" };
    format!("{prefix}{}\n", style.section(group_name))
}
