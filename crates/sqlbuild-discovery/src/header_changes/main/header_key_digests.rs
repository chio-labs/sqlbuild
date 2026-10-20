//! A model header's keys as short value digests.

use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::header_changes::_helpers::value_encoding::value_digest;
use crate::header_changes::types::HeaderKeys;

/// Each header key with its value's short digest, sorted by key.
#[must_use]
pub fn header_key_digests(values: &[(String, AuthoredValue)]) -> HeaderKeys {
    let mut keys: HeaderKeys = values
        .iter()
        .map(|(key, value)| (key.clone(), value_digest(value)))
        .collect();
    keys.sort();
    keys
}
