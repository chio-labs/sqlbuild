//! The `sqb dbt init --dry-run` preview.

use crate::cli_text::models::{CliDocument, CliStyle};
use crate::dbt_command::models::DbtInitSummary;
use crate::text::main::python_isspace::python_isspace;

/// A blank line, the preview fields, and the generated configuration.
#[must_use]
pub fn render_dbt_init_preview(summary: &DbtInitSummary, style: CliStyle) -> String {
    let mut document: CliDocument = CliDocument::new(style);
    document.header("SQLBuild project preview", None);
    document.lines.push(String::new());
    document.field("Project", (&summary.project_name, " "));
    document.field("Config file", (&summary.project_file, "  "));
    document.field("Adapter", (&summary.adapter, " "));
    document.field("Target", (&summary.target_name, "  "));
    document.field("Profile", (&summary.profile_name, " "));
    document.lines.push(String::new());
    document.section("Generated config");
    document
        .lines
        .push(summary.toml.trim_end_matches(python_isspace).to_owned());
    format!("\n{}", document.render(true))
}
