//! The summary printed after a project is created.

use crate::cli_text::models::{CliDocument, CliStyle};
use crate::constants::PROJECT_CONFIG_FILENAME;
use crate::init_command::constants::NEXT_STEPS;

/// The created header, project and config fields, and the numbered next steps.
#[must_use]
pub fn render_init_summary(project_name: &str, style: CliStyle) -> String {
    let mut document: CliDocument = CliDocument::new(style);
    document.header("SQLBuild project created", None);
    document.lines.push(String::new());
    document.field("Project", (project_name, " "));
    document.field("Config", (PROJECT_CONFIG_FILENAME, "  "));
    document.lines.push(String::new());
    document.section("Next steps");
    document
        .lines
        .extend(NEXT_STEPS.iter().map(|step| (*step).to_owned()));
    document.command_line("  7. ", ("sqb compile", true));
    document.command_line("  8. ", ("sqb build", true));
    document.render(true)
}
