//! Resolve format and lint settings from the project's configuration files.

use std::path::Path;

use crate::lint_text::_helpers::settings::{adapter_dialect, positive_int, read_table};
use crate::lint_text::constants::{
    DEFAULT_DIALECT, DEFAULT_LINE_WIDTH, DEFAULT_MAX_DESCRIPTION_LINES, DEFAULT_MAX_LITERAL_LENGTH,
    DEFAULT_MAX_RANKING_ORDER_BY, LOCAL_CONFIG_FILENAME,
};
use crate::lint_text::models::FormatSettings;
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;

/// `[format]` widths, rule thresholds and the adapter dialect, the local adapter winning.
pub fn resolve_format_settings(project_dir: &Path) -> Result<FormatSettings, String> {
    let project: Option<toml::Table> = read_table(&project_dir.join(PROJECT_CONFIG_FILENAME))?;
    let format_section: Option<&toml::Table> = project
        .as_ref()
        .and_then(|table| table.get("format"))
        .and_then(toml::Value::as_table);
    let thresholds: Option<&toml::Table> = project
        .as_ref()
        .and_then(|table| table.get("rules"))
        .and_then(toml::Value::as_table)
        .and_then(|rules| rules.get("thresholds"))
        .and_then(toml::Value::as_table);
    let mut dialect: String = project
        .as_ref()
        .and_then(adapter_dialect)
        .unwrap_or_else(|| DEFAULT_DIALECT.to_owned());
    if let Some(local) = read_table(&project_dir.join(LOCAL_CONFIG_FILENAME))?
        && let Some(local_dialect) = adapter_dialect(&local)
    {
        dialect = local_dialect;
    }
    Ok(FormatSettings {
        line_width: positive_int(format_section, "line_width", DEFAULT_LINE_WIDTH),
        max_description_lines: positive_int(
            format_section,
            "max_description_lines",
            DEFAULT_MAX_DESCRIPTION_LINES,
        ),
        dialect,
        max_literal_length: positive_int(
            thresholds,
            "max_literal_length",
            DEFAULT_MAX_LITERAL_LENGTH,
        ),
        max_ranking_order_by: positive_int(
            thresholds,
            "max_ranking_order_by",
            DEFAULT_MAX_RANKING_ORDER_BY,
        ),
        has_project_config: project.is_some(),
    })
}
