//! Whether a loaded dbt config file holds a top-level mapping.

use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::DbtYamlValue;

/// Accept an empty document or a mapping; anything else is not a dbt config file.
pub fn dbt_yaml_mapping(file: &str, document: &DbtYamlValue) -> Result<(), DbtProfileError> {
    match document {
        DbtYamlValue::Null | DbtYamlValue::Mapping { .. } => Ok(()),
        DbtYamlValue::Text(_) | DbtYamlValue::Other => Err(DbtProfileError(format!(
            "{file} must contain a top-level mapping"
        ))),
    }
}
