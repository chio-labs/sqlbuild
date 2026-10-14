//! Record the declared-columns hash in fingerprint metadata.

use serde_json::Value;

use crate::planner_changes::_helpers::json_payload::{canonical_text, decoded_object};
use crate::planner_changes::constants::DECLARED_COLUMNS_METADATA_KEY;

/// Canonical metadata JSON that also records `declared_columns_hash`; text that is not an object is returned unchanged.
pub fn with_declared_columns_hash(metadata_json: &str, declared_columns_hash: &str) -> String {
    match decoded_object(metadata_json) {
        Ok(Some(mut object)) => {
            object.insert(
                DECLARED_COLUMNS_METADATA_KEY.to_owned(),
                Value::String(declared_columns_hash.to_owned()),
            );
            canonical_text(object)
        }
        _ => metadata_json.to_owned(),
    }
}
