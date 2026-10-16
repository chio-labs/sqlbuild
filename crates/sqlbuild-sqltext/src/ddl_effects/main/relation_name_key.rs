//! The cache invalidation key of one relation name.

use crate::ddl_effects::_helpers::names::name_key;

/// The invalidation key for one unquoted or quoted unqualified relation name.
#[must_use]
pub fn relation_name_key(name: &str) -> String {
    name_key(name)
}
