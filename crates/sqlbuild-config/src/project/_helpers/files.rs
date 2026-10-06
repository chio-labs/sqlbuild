//! Locate and load configuration files as the Python loader does.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::toml::main::load_toml::load_toml;
use std::path::Path;

/// Reject a legacy YAML file that has no TOML replacement, as the Python loader does.
pub(crate) fn reject_legacy(
    directory: &Path,
    filename: &str,
    legacy_filename: &str,
) -> Result<(), ConfigError> {
    if !directory.join(filename).exists() && directory.join(legacy_filename).exists() {
        return Err(ConfigError::new(
            ConfigErrorKind::InvalidField,
            format!("{legacy_filename} is no longer supported; rename it to {filename}"),
        ));
    }
    Ok(())
}

/// Read and parse one TOML file the way `tomllib.load` does.
pub(crate) fn load_toml_file(path: &Path) -> Result<ConfigValue, ConfigError> {
    let bytes = std::fs::read(path).map_err(|error| {
        ConfigError::new(
            ConfigErrorKind::Missing,
            format!("{}: {error}", path.display()),
        )
    })?;
    let text = String::from_utf8(bytes).map_err(|error| {
        ConfigError::new(ConfigErrorKind::Syntax, format!("invalid UTF-8: {error}"))
    })?;
    load_toml(&text)
}
