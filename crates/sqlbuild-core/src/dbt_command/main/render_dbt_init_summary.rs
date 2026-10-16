//! The summary written after `sqb dbt init` creates a twin project.

use crate::cli_text::models::{CliDocument, CliStyle};
use crate::constants::PROJECT_CONFIG_FILENAME;
use crate::dbt_command::constants::FIELD_LABEL_WIDTH;
use crate::dbt_command::models::DbtInitSummary;

/// A blank line, the setup fields, what was created, and the next steps.
#[must_use]
pub fn render_dbt_init_summary(summary: &DbtInitSummary, style: CliStyle) -> String {
    let mut document: CliDocument = CliDocument::new(style);
    document.header("SQLBuild project created", None);
    document.lines.push(String::new());
    document.section("Setup summary");
    let rows: Vec<(String, String)> = [
        ("Project", &summary.project_name),
        ("Config file", &summary.project_file),
        ("Adapter", &summary.adapter),
        ("Target", &summary.target_name),
        ("Profile", &summary.profile_name),
    ]
    .iter()
    .map(|(label, value)| ((*label).to_owned(), (*value).clone()))
    .collect();
    document.fields(&rows, Some(FIELD_LABEL_WIDTH));
    document.lines.push(String::new());
    document.section("What SQLBuild created");
    document.lines.push(format!(
        "  1. {} ({})",
        style.value("SQLBuild twin config"),
        style.object_name(PROJECT_CONFIG_FILENAME)
    ));
    document.lines.push(
        "     This points SQLBuild at your dbt project and profile. Edit it if dbt paths"
            .to_owned(),
    );
    document
        .lines
        .push("     or profile targets need to change.".to_owned());
    document.lines.push(String::new());
    document.section("Next steps");
    document.command_line("  1. ", (&format!("cd {}", summary.output_dir), true));
    document.lines.push(format!(
        "  2. {}",
        style.warning("Review the config file above.")
    ));
    document.command_line("  3. ", ("sqb dbt debug", true));
    document.command_line("  4. ", ("sqb dbt build", true));
    format!("\n{}", document.render(true))
}
