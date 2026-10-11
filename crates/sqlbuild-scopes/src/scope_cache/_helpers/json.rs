//! Python's canonical cache JSON (`ensure_ascii`, compact separators, sorted keys) and SHA-256.

use sha2::{Digest, Sha256};
use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

/// The canonical JSON text, or why Python's encoder raises.
pub(crate) fn canonical_json(value: &JsonValue) -> Result<String, JsonEmitError> {
    let mut options: StdlibJsonOptions = StdlibJsonOptions::new(None).with_separators(",", ":");
    options.sort_keys = true;
    dumps(value, &JsonDialect::Stdlib(options))
}

/// The lowercase hex SHA-256 of `bytes`.
pub(crate) fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut text: String = String::with_capacity(digest.len() * 2);
    for byte in digest {
        text.push_str(&format!("{byte:02x}"));
    }
    text
}

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(crate) fn optional_text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, text)
}

pub(crate) fn integer(value: i64) -> JsonValue {
    match JsonInteger::parse(&value.to_string()) {
        Some(number) => JsonValue::Integer(number),
        None => JsonValue::Null,
    }
}

pub(crate) fn optional_integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, integer)
}

pub(crate) fn object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        fields
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}
