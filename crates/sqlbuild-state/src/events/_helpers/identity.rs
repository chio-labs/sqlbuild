//! Content-addressed event IDs: SHA-256 of a compact, ASCII-escaped JSON identity array.

use sha2::{Digest, Sha256};
use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::events::constants::{COMPACT_ITEM_SEPARATOR, COMPACT_KEY_SEPARATOR};
use crate::events::models::EventRelation;

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(crate) fn optional_text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, text)
}

/// `MigrationRelation.identity`: lowercased database or null, schema or `""`, and name.
pub(crate) fn relation_identity(relation: &EventRelation) -> JsonValue {
    JsonValue::Array(vec![
        optional_text(
            relation
                .database
                .as_deref()
                .map(str::to_lowercase)
                .as_deref(),
        ),
        text(
            &relation
                .schema
                .as_deref()
                .unwrap_or_default()
                .to_lowercase(),
        ),
        text(&relation.name.to_lowercase()),
    ])
}

/// `sha256(json.dumps(value, separators=(",", ":"), ensure_ascii=True))` as hex.
pub(crate) fn json_digest(value: &JsonValue, sort_keys: bool) -> Result<String, JsonEmitError> {
    let options = StdlibJsonOptions {
        sort_keys,
        ..StdlibJsonOptions::new(None)
            .with_separators(COMPACT_ITEM_SEPARATOR, COMPACT_KEY_SEPARATOR)
    };
    let encoded: String = dumps(value, &JsonDialect::Stdlib(options))?;
    Ok(format!("{:x}", Sha256::digest(encoded.as_bytes())))
}
