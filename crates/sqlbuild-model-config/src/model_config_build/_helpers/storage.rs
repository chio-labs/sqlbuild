//! The built values without storage keys, and the header's keys.

use crate::config_values::main::config_entry::config_entry;
use crate::config_values::main::same_config_key::same_config_key;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::ConfigEntries;
use crate::config_values::types::HostObject;
use crate::model_config_build::_helpers::checks::key_text;
use crate::model_config_build::constants::{
    FULL_REFRESH_KEY, INCREMENTAL_MATERIALIZATION, MATERIALIZED_KEY, RETENTION_KEY, TABLE_TYPE_KEY,
};
use crate::model_config_build::models::ConfigBuildHalt;
use crate::types::AuthoredNode;

/// Config entries.
type Entries<H> = ConfigEntries<H>;

/// Whether `key` names a storage setting, which the config values leave out.
fn storage_key<H: HostObject>(key: &ConfigNode<H>) -> bool {
    key.is_text(RETENTION_KEY) || key.is_text(TABLE_TYPE_KEY)
}

/// Drop storage keys, then `full_refresh` where `build_model_config` drops it.
pub(crate) fn storage_free_values<H: HostObject>(
    resolved: Entries<H>,
    header: &[(ConfigNode<H>, ConfigNode<H>)],
) -> Entries<H> {
    let mut values: Entries<H> = resolved
        .into_iter()
        .filter(|(key, _)| !storage_key(key))
        .collect();
    let incremental: bool = config_entry(&values, MATERIALIZED_KEY)
        .is_some_and(|value| value.is_text(INCREMENTAL_MATERIALIZATION));
    if config_entry(header, FULL_REFRESH_KEY).is_none() && !incremental {
        let refresh = ConfigNode::Str(FULL_REFRESH_KEY.to_owned());
        values.retain(|(key, _)| !same_config_key(key, &refresh));
    }
    values
}

/// The header's keys sorted by code point; a key that is not a string halts.
pub(crate) fn sorted_header_keys<H: HostObject, E>(
    header: &[(ConfigNode<H>, ConfigNode<H>)],
) -> Result<Vec<String>, ConfigBuildHalt<H, E>> {
    let mut keys: Vec<String> = Vec::with_capacity(header.len());
    for (key, _) in header {
        match (key_text(key), key) {
            (Some(text), _) => keys.push(text),
            (None, ConfigNode::Host(host)) if host.facts.text.is_some() => {
                keys.push(host.facts.text.clone().unwrap_or_default());
            }
            (None, _) => return Err(ConfigBuildHalt::KeyNotText(key.clone())),
        }
    }
    keys.sort();
    Ok(keys)
}
