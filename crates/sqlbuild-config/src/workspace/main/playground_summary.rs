//! The summary printed after a playground is created.

use sqlbuild_core::cli_text::models::{CliDocument, CliStyle};

use crate::workspace::_helpers::playground::{example_name, suggested_commands};

/// `render_playground_completion_text`.
#[must_use]
pub fn playground_summary(display_path: &str, template: &str, style: CliStyle) -> String {
    let mut document: CliDocument = CliDocument::new(style);
    document.header("SQLBuild playground created", None);
    document.lines.push(String::new());
    document.field("Project", (display_path, " "));
    document.field("Adapter", ("DuckDB", " "));
    document.field("Example", (example_name(template), " "));
    document.lines.push(String::new());
    document.title_section("Try");
    document.commands(&suggested_commands(template, display_path), (false, false));
    document.render(true)
}
