//! Reading the project and local configuration documents for Recall.

use std::path::Path;

use sqlbuild_config::models::ConfigValue;
use sqlbuild_config::toml::main::load_toml::load_toml;

use crate::settings::errors::SettingsError;

/// The root table of a TOML file, `None` when it does not exist.
pub(crate) fn read_document(path: &Path) -> Result<Option<ConfigValue>, SettingsError> {
    let text = match std::fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(SettingsError::new(format!(
                "cannot read {}: {error}",
                path.display()
            )));
        }
    };
    load_toml(&text).map(Some).map_err(|error| {
        SettingsError::new(format!(
            "{} is not valid TOML: {}",
            path.display(),
            error.message
        ))
    })
}

/// The value at a dotted path of tables.
pub(crate) fn lookup<'a>(
    document: Option<&'a ConfigValue>,
    path: &[&str],
) -> Option<&'a ConfigValue> {
    let mut value: &ConfigValue = document?;
    for key in path {
        value = value.get(key)?;
    }
    Some(value)
}

pub(crate) fn string_at(document: Option<&ConfigValue>, path: &[&str]) -> Option<String> {
    match lookup(document, path)? {
        ConfigValue::String(text) if !text.trim().is_empty() => Some(text.trim().to_owned()),
        _ => None,
    }
}

/// Replace `${env:NAME}` with the environment variable, failing when it is unset.
pub(crate) fn expand_environment(text: &str, label: &str) -> Result<String, SettingsError> {
    let mut expanded = String::with_capacity(text.len());
    let mut rest = text;
    while let Some(start) = rest.find("${env:") {
        expanded.push_str(&rest[..start]);
        let after = &rest[start + "${env:".len()..];
        let Some(end) = after.find('}') else {
            return Err(SettingsError::new(format!(
                "{label} has an unterminated ${{env:...}} reference"
            )));
        };
        let name = &after[..end];
        let value = std::env::var(name).map_err(|_| {
            SettingsError::new(format!(
                "{label} references unset environment variable {name}"
            ))
        })?;
        expanded.push_str(&value);
        rest = &after[end + 1..];
    }
    expanded.push_str(rest);
    Ok(expanded)
}
