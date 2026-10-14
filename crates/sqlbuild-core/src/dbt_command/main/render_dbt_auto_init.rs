//! The notice written when a dbt command creates its SQLBuild twin.

use crate::cli_text::models::{CliDocument, CliStyle};
use crate::dbt_command::constants::FIELD_LABEL_WIDTH;

/// A blank line, the created header, the config file, and what was created.
#[must_use]
pub fn render_dbt_auto_init(project_file: &str, style: CliStyle) -> String {
    let mut document: CliDocument = CliDocument::new(style);
    document.header("SQLBuild dbt setup created", None);
    document.lines.push(String::new());
    document.section("Setup summary");
    document.fields(
        &[("Config file".to_owned(), project_file.to_owned())],
        Some(FIELD_LABEL_WIDTH),
    );
    document.lines.push(String::new());
    document.lines.push(format!(
        "{}: a twin config that points SQLBuild at your dbt project and profile.",
        style.value("What SQLBuild created")
    ));
    format!("\n{}", document.render(true))
}
