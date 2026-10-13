//! The header announcing the selected seeds.

use crate::cli_text::main::format_surface_header::format_surface_header;
use crate::cli_text::main::format_tree_connector::format_tree_connector;
use crate::cli_text::models::CliStyle;

/// `Seed ready  <n> selected`, then the `Seeds (<n>)` tree and a blank line.
#[must_use]
pub fn render_seed_ready(names: &[String], style: CliStyle) -> String {
    let count: usize = names.len();
    let mut text: String = format!(
        "\n{}\n\n{}\n",
        format_surface_header(style, "Seed ready", &format!("{count} selected")),
        style.section(&format!("Seeds ({count})"))
    );
    for (index, name) in names.iter().enumerate() {
        text.push_str(&format!(
            "{} {name}\n",
            format_tree_connector(style, index + 1 == count)
        ));
    }
    text.push('\n');
    text
}
