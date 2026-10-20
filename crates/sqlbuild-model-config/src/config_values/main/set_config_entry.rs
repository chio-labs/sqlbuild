//! One set entry of a config mapping.

use crate::config_values::_helpers::entries::set_entry;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;

/// Python's `mapping.get(key)` for a string `key`, unless it is absent or `None`.
#[must_use]
pub fn set_config_entry<'a, H: HostObject>(
    entries: &'a [(ConfigNode<H>, ConfigNode<H>)],
    key: &str,
) -> Option<&'a ConfigNode<H>> {
    set_entry(entries, key)
}
