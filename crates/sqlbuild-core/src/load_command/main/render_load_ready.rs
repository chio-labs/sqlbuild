//! The header announcing how many loads were selected.

use crate::cli_text::main::format_surface_header::format_surface_header;
use crate::cli_text::models::CliStyle;

/// A blank line, `Load ready  <n> selected`, and a blank line.
#[must_use]
pub fn render_load_ready(selected: usize, style: CliStyle) -> String {
    format!(
        "\n{}\n\n",
        format_surface_header(style, "Load ready", &format!("{selected} selected"))
    )
}
