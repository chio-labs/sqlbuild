//! The project name, profile name and target path `dbt_project.yml` defines.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::dbt_profile::constants::DEFAULT_DBT_TARGET_PATH;
use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::{DbtProjectMetadata, DbtYamlValue};

fn required_text(file: &str, key: &str, value: &DbtYamlValue) -> Result<String, DbtProfileError> {
    if let DbtYamlValue::Text(text) = value {
        let stripped: &str = python_strip(text);
        if !stripped.is_empty() {
            return Ok(stripped.to_owned());
        }
    }
    Err(DbtProfileError(format!(
        "{file} must define non-empty string '{key}'"
    )))
}

/// Validate `name`, `profile` and `target-path` from `dbt_project.yml`, stripping each.
pub fn dbt_project_metadata(
    file: &str,
    (name, profile, target_path): (&DbtYamlValue, &DbtYamlValue, &DbtYamlValue),
) -> Result<DbtProjectMetadata, DbtProfileError> {
    let project_name: String = required_text(file, "name", name)?;
    let profile_name: String = required_text(file, "profile", profile)?;
    let target_path: String = match target_path {
        DbtYamlValue::Null => DEFAULT_DBT_TARGET_PATH.to_owned(),
        DbtYamlValue::Text(text) if !python_strip(text).is_empty() => python_strip(text).to_owned(),
        DbtYamlValue::Text(_) | DbtYamlValue::Mapping { .. } | DbtYamlValue::Other => {
            return Err(DbtProfileError(format!(
                "{file} target-path must be a non-empty string"
            )));
        }
    };
    Ok(DbtProjectMetadata {
        project_name,
        profile_name,
        target_path,
    })
}
