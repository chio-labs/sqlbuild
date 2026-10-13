//! The header announcing the selected tests.

use crate::cli_text::main::format_surface_header::format_surface_header;
use crate::cli_text::models::CliStyle;

/// A blank line, `Test ready  <n> selected, <m> models`, and a blank line.
#[must_use]
pub fn render_test_ready((tests, models): (usize, usize), style: CliStyle) -> String {
    format!(
        "\n{}\n\n",
        format_surface_header(
            style,
            "Test ready",
            &format!("{tests} selected, {models} models")
        )
    )
}
