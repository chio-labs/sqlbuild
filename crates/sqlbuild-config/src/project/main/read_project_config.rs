//! Read the discovery fields of `sqlbuild_project.toml`.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::project::_helpers::fields::{
    flag, key_text, lookup, optional_text, required_text, section, section_keys, text_mapping,
};
use crate::project::_helpers::files::{load_toml_file, reject_legacy};
use crate::project::constants::{
    LEGACY_PROJECT_CONFIG_FILENAME, LEGACY_SQL_VALIDATION_KEY, PROJECT_CONFIG_FILENAME,
    REQUIRE_SQL_ANALYSIS_KEY, SQL_ANALYSIS_KEY,
};
use crate::project::models::{ProjectConfigFile, ProjectSettings};
use std::path::Path;

fn settings(table: &ConfigValue) -> Result<ProjectSettings, ConfigError> {
    let entries = section(table, "settings")?;
    let current = lookup(entries, SQL_ANALYSIS_KEY);
    let legacy = lookup(entries, LEGACY_SQL_VALIDATION_KEY);
    if current.is_some() && legacy.is_some() && current != legacy {
        return Err(ConfigError::new(
            ConfigErrorKind::InvalidField,
            "settings.sql_analysis conflicts with legacy settings.sql_validation",
        ));
    }
    let analysis_key = if current.is_some() {
        SQL_ANALYSIS_KEY
    } else {
        LEGACY_SQL_VALIDATION_KEY
    };
    Ok(ProjectSettings {
        sql_analysis: flag(entries, analysis_key, true)?,
        require_sql_analysis: flag(entries, REQUIRE_SQL_ANALYSIS_KEY, false)?,
    })
}

fn path_defaults(table: &ConfigValue) -> Result<Vec<(String, ConfigValue)>, ConfigError> {
    section(table, "path_defaults")?
        .iter()
        .map(|(key, value)| {
            let name = key_text(key)?;
            match value {
                ConfigValue::Map(_) => Ok((name, value.clone())),
                _ => Err(ConfigError::new(
                    ConfigErrorKind::InvalidField,
                    format!("path_defaults['{name}'] must be a mapping"),
                )),
            }
        })
        .collect()
}

/// Read `sqlbuild_project.toml` in `project_dir`; Python's loader remains the full validator.
pub fn read_project_config(project_dir: &Path) -> Result<ProjectConfigFile, ConfigError> {
    reject_legacy(
        project_dir,
        PROJECT_CONFIG_FILENAME,
        LEGACY_PROJECT_CONFIG_FILENAME,
    )?;
    let table = load_toml_file(&project_dir.join(PROJECT_CONFIG_FILENAME))?;
    Ok(ProjectConfigFile {
        name: required_text(&table, "name")?,
        adapter: required_text(&table, "adapter")?,
        default_target: optional_text(&table, "default_target")?,
        settings: settings(&table)?,
        enforce_placement: flag(section(&table, "scopes")?, "enforce_placement", true)?,
        enforce_explicit_references: flag(
            section(&table, "references")?,
            "enforce_explicit",
            true,
        )?,
        vars: text_mapping(&table, "vars")?,
        path_defaults: path_defaults(&table)?,
        target_names: section_keys(&table, "targets")?,
    })
}
