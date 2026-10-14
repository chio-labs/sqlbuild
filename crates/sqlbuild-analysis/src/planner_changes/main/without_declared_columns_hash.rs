//! Drop the declared-columns hash from fingerprint metadata.

use crate::planner_changes::_helpers::json_payload::{canonical_text, decoded_object};
use crate::planner_changes::constants::DECLARED_COLUMNS_METADATA_KEY;

/// Canonical metadata JSON without the declared-columns hash, or the text unchanged when it has none.
pub fn without_declared_columns_hash(metadata_json: &str) -> String {
    match decoded_object(metadata_json) {
        Ok(Some(mut object)) if object.contains_key(DECLARED_COLUMNS_METADATA_KEY) => {
            object.shift_remove(DECLARED_COLUMNS_METADATA_KEY);
            canonical_text(object)
        }
        _ => metadata_json.to_owned(),
    }
}
