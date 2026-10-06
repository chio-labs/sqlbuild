//! Typed reads of configuration fields with the Python loader's defaults and type checks.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;

fn invalid(field: &str, expected: &str) -> ConfigError {
    ConfigError::new(
        ConfigErrorKind::InvalidField,
        format!("{field} must be {expected}"),
    )
}

/// A section as a mapping; a missing section is empty, as in `_coerce_mapping`.
pub(crate) fn section<'value>(
    table: &'value ConfigValue,
    key: &str,
) -> Result<&'value [(ConfigValue, ConfigValue)], ConfigError> {
    match table.get(key) {
        None | Some(ConfigValue::Null) => Ok(&[]),
        Some(value) => value.as_map().ok_or_else(|| invalid(key, "a mapping")),
    }
}

/// A non-empty string, stripped, as in `_require_str`.
pub(crate) fn required_text(table: &ConfigValue, key: &str) -> Result<String, ConfigError> {
    optional_text(table, key)?.ok_or_else(|| invalid(key, "a non-empty string"))
}

/// An optional non-empty string, stripped, as in `_optional_str`.
pub(crate) fn optional_text(table: &ConfigValue, key: &str) -> Result<Option<String>, ConfigError> {
    match table.get(key) {
        None | Some(ConfigValue::Null) => Ok(None),
        Some(ConfigValue::String(text)) if !text.trim().is_empty() => {
            Ok(Some(text.trim().to_owned()))
        }
        Some(_) => Err(invalid(key, "a non-empty string")),
    }
}

/// An optional boolean with a default, as in `_optional_bool`.
pub(crate) fn flag(
    entries: &[(ConfigValue, ConfigValue)],
    key: &str,
    default: bool,
) -> Result<bool, ConfigError> {
    match lookup(entries, key) {
        None | Some(ConfigValue::Null) => Ok(default),
        Some(ConfigValue::Bool(value)) => Ok(*value),
        Some(_) => Err(invalid(key, "a boolean")),
    }
}

/// The value of a string key among mapping entries.
pub(crate) fn lookup<'value>(
    entries: &'value [(ConfigValue, ConfigValue)],
    key: &str,
) -> Option<&'value ConfigValue> {
    entries
        .iter()
        .find(|(candidate, _)| matches!(candidate, ConfigValue::String(text) if text == key))
        .map(|(_, value)| value)
}

/// The text of a mapping key; TOML keys are always strings.
pub(crate) fn key_text(key: &ConfigValue) -> Result<String, ConfigError> {
    match key {
        ConfigValue::String(text) => Ok(text.clone()),
        _ => Err(invalid("a key", "a string")),
    }
}

/// String values, as in `_load_string_mapping`.
pub(crate) fn text_mapping(
    table: &ConfigValue,
    key: &str,
) -> Result<Vec<(String, String)>, ConfigError> {
    section(table, key)?
        .iter()
        .map(|(name, value)| match value {
            ConfigValue::String(text) => Ok((key_text(name)?, text.clone())),
            _ => Err(invalid(&format!("{key}.{}", key_text(name)?), "a string")),
        })
        .collect()
}

/// The keys of a section, in document order.
pub(crate) fn section_keys(table: &ConfigValue, key: &str) -> Result<Vec<String>, ConfigError> {
    section(table, key)?
        .iter()
        .map(|(name, _)| key_text(name))
        .collect()
}
