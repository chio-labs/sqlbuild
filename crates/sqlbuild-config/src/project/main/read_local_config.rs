//! Read the discovery fields of `sqlbuild_local.toml`.

use crate::errors::ConfigError;
use crate::project::_helpers::fields::{
    flag, lookup, optional_text, section, section_keys, text_mapping,
};
use crate::project::_helpers::files::{load_toml_file, reject_legacy};
use crate::project::constants::{
    LEGACY_LOCAL_CONFIG_FILENAME, LEGACY_SQL_VALIDATION_KEY, LOCAL_CONFIG_FILENAME,
    SQL_ANALYSIS_KEY,
};
use crate::project::models::LocalConfigFile;
use std::path::Path;

/// Read `sqlbuild_local.toml` in `project_dir`, or the defaults when it does not exist.
pub fn read_local_config(project_dir: &Path) -> Result<LocalConfigFile, ConfigError> {
    reject_legacy(
        project_dir,
        LOCAL_CONFIG_FILENAME,
        LEGACY_LOCAL_CONFIG_FILENAME,
    )?;
    let path = project_dir.join(LOCAL_CONFIG_FILENAME);
    if !path.exists() {
        return Ok(LocalConfigFile::default());
    }
    let table = load_toml_file(&path)?;
    let settings = section(&table, "settings")?;
    let analysis_key = [SQL_ANALYSIS_KEY, LEGACY_SQL_VALIDATION_KEY]
        .into_iter()
        .find(|key| lookup(settings, key).is_some());
    Ok(LocalConfigFile {
        target: optional_text(&table, "target")?,
        adapter: optional_text(&table, "adapter")?,
        sql_analysis: analysis_key
            .map(|key| flag(settings, key, true))
            .transpose()?,
        vars: text_mapping(&table, "vars")?,
        target_names: section_keys(&table, "targets")?,
    })
}
