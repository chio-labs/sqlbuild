//! A config mapping with one entry set.

use crate::config_values::_helpers::entries::inserted;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::ConfigEntries;
use crate::config_values::types::HostObject;

/// `entries` after `mapping[key] = value`: an equal key keeps its place, else the entry is appended.
#[must_use]
pub fn inserted_entry<H: HostObject>(
    entries: ConfigEntries<H>,
    key: ConfigNode<H>,
    value: ConfigNode<H>,
) -> ConfigEntries<H> {
    inserted(entries, key, value)
}
