//! One entry of a config mapping.

use crate::config_values::_helpers::entries::entry;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;

/// Python's `mapping.get(key)` for a string `key`.
#[must_use]
pub fn config_entry<'a, H: HostObject>(
    entries: &'a [(ConfigNode<H>, ConfigNode<H>)],
    key: &str,
) -> Option<&'a ConfigNode<H>> {
    entry(entries, key)
}
