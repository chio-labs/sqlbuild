//! `operation_metadata_field`: whether a key is an allow-listed operation metadata field.

use crate::lifecycle_events::constants::OPERATION_METADATA_FIELDS;

/// Whether a metadata key, when a string, is an allow-listed operation metadata field.
#[must_use]
pub fn operation_metadata_field(key: Option<&str>) -> bool {
    key.is_some_and(|key| OPERATION_METADATA_FIELDS.contains(&key))
}
