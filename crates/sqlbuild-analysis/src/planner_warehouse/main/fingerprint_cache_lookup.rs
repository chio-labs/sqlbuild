//! Validate one stored migration fingerprint cache entry.

use crate::planner_warehouse::_helpers::cache_entries::entry_digest;
use crate::planner_warehouse::constants::{
    FINGERPRINT_CACHE_ENTRY_SEPARATOR, FINGERPRINT_CACHE_VERSION,
    MAX_FINGERPRINT_CACHE_ENTRY_CHARACTERS,
};
use serde_json::Value;

/// The stored fingerprint (possibly `None`), or `None` when the entry is not valid for the key.
pub fn fingerprint_cache_lookup(
    contents: &str,
    expected_cache_key: &str,
) -> Option<Option<String>> {
    if contents.chars().count() > MAX_FINGERPRINT_CACHE_ENTRY_CHARACTERS {
        return None;
    }
    let (stored_digest, serialized) = contents.split_once(FINGERPRINT_CACHE_ENTRY_SEPARATOR)?;
    if !stored_digest.is_ascii() || stored_digest != entry_digest(expected_cache_key, serialized) {
        return None;
    }
    let Ok(Value::Object(values)) = serde_json::from_str::<Value>(serialized) else {
        return None;
    };
    let version_matches = match values.get("v") {
        Some(Value::Number(number)) => number.as_f64() == Some(FINGERPRINT_CACHE_VERSION as f64),
        Some(Value::Bool(flag)) => *flag,
        _ => false,
    };
    let key_matches = values.get("k").and_then(Value::as_str) == Some(expected_cache_key);
    if !version_matches || !key_matches {
        return None;
    }
    match values.get("f") {
        None | Some(Value::Null) => Some(None),
        Some(Value::String(fingerprint)) => Some(Some(fingerprint.clone())),
        Some(_) => None,
    }
}
