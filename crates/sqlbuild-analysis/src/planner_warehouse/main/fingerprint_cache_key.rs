//! The persistent key of one migration fingerprint cache entry.

use crate::planner_warehouse::models::FingerprintCacheKey;
use sha2::{Digest, Sha256};
use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// SHA-256 of the compact, non-ASCII-escaped JSON array of the key parts.
pub fn fingerprint_cache_key(key: &FingerprintCacheKey) -> Result<String, JsonEmitError> {
    let renames: Vec<JsonValue> = key
        .visible_renames
        .iter()
        .map(|(name, identity)| {
            JsonValue::Array(vec![
                JsonValue::String(name.clone()),
                JsonValue::String(identity.clone()),
            ])
        })
        .collect();
    let value = JsonValue::Array(vec![
        JsonValue::String(key.shared_digest.clone()),
        JsonValue::String(key.query_sql.clone()),
        JsonValue::String(key.metadata_json.clone()),
        key.dialect
            .clone()
            .map_or(JsonValue::Null, JsonValue::String),
        JsonValue::Array(renames),
    ]);
    let options = StdlibJsonOptions {
        ensure_ascii: false,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    let text = dumps(&value, &JsonDialect::Stdlib(options))?;
    Ok(format!("{:x}", Sha256::digest(text.as_bytes())))
}
