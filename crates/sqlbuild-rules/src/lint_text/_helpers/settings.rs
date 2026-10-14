//! Read format settings from parsed configuration tables.

use std::fs;
use std::path::Path;

use crate::lint_text::constants::ADAPTER_DIALECT_TRANSLATIONS;

/// The parsed TOML file at `path`, or `None` when it is not a file.
pub(crate) fn read_table(path: &Path) -> Result<Option<toml::Table>, String> {
    if !path.is_file() {
        return Ok(None);
    }
    let text: String = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let text: &str = text.strip_prefix('\u{feff}').unwrap_or(&text);
    toml::from_str(text)
        .map(Some)
        .map_err(|error| error.to_string())
}

/// The dialect a configured adapter name selects.
pub(crate) fn adapter_dialect(table: &toml::Table) -> Option<String> {
    let adapter: &str = table.get("adapter")?.as_str()?;
    let dialect: &str = ADAPTER_DIALECT_TRANSLATIONS
        .iter()
        .find(|(name, _)| *name == adapter)
        .map_or(adapter, |(_, dialect)| dialect);
    Some(dialect.to_owned())
}

/// A positive integer `key` of `section`, or `current`.
pub(crate) fn positive_int(section: Option<&toml::Table>, key: &str, current: i64) -> i64 {
    section
        .and_then(|section| section.get(key))
        .and_then(toml::Value::as_integer)
        .filter(|value| *value > 0)
        .unwrap_or(current)
}
