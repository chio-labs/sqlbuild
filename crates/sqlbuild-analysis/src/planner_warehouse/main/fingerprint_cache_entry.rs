//! The stored payload of one migration fingerprint cache entry.

use crate::planner_warehouse::_helpers::cache_entries::entry_digest;
use crate::planner_warehouse::constants::{
    FINGERPRINT_CACHE_ENTRY_SEPARATOR, FINGERPRINT_CACHE_VERSION,
};
use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

/// `digest` newline `{"f":...,"k":...,"v":1}`, the digest binding the payload to its key.
pub fn fingerprint_cache_entry(
    cache_key: &str,
    fingerprint: Option<&str>,
) -> Result<String, JsonEmitError> {
    let value = JsonValue::Object(vec![
        (
            "v".to_owned(),
            JsonValue::Integer(JsonInteger::from(FINGERPRINT_CACHE_VERSION)),
        ),
        ("k".to_owned(), JsonValue::String(cache_key.to_owned())),
        (
            "f".to_owned(),
            fingerprint.map_or(JsonValue::Null, |text| JsonValue::String(text.to_owned())),
        ),
    ]);
    let options = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    let serialized = dumps(&value, &JsonDialect::Stdlib(options))?;
    Ok(format!(
        "{}{FINGERPRINT_CACHE_ENTRY_SEPARATOR}{serialized}",
        entry_digest(cache_key, &serialized)
    ))
}
