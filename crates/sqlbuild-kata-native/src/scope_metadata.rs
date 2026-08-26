use serde::{Deserialize, Deserializer};

use crate::constants::SCOPE_METADATA_SCHEMA_VERSION;

pub(crate) fn deserialize_scope_schema_version<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    let version = u32::deserialize(deserializer)?;
    if version != SCOPE_METADATA_SCHEMA_VERSION {
        return Err(serde::de::Error::custom(format!(
            "unsupported scope metadata schema version {version}; expected {SCOPE_METADATA_SCHEMA_VERSION}"
        )));
    }
    Ok(version)
}
