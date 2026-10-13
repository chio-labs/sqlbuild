//! `data_version_hash`: the stable source freshness identity used as a graph input.

use sha2::{Digest, Sha256};
use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::freshness::constants::{
    COMPACT_ITEM_SEPARATOR, COMPACT_KEY_SEPARATOR, DATA_VERSION_KEY, SOURCE_NAME_KEY, STRATEGY_KEY,
    VALUE_KIND_KEY,
};

/// SHA-256 of the compact, key-sorted JSON of the four identity fields.
pub fn data_version_hash(
    (source_name, strategy): (&str, &str),
    value_kind: &str,
    data_version: &str,
) -> Result<String, JsonEmitError> {
    let payload = JsonValue::Object(
        [
            (SOURCE_NAME_KEY, source_name),
            (STRATEGY_KEY, strategy),
            (VALUE_KIND_KEY, value_kind),
            (DATA_VERSION_KEY, data_version),
        ]
        .into_iter()
        .map(|(key, value)| (key.to_owned(), JsonValue::String(value.to_owned())))
        .collect(),
    );
    let options = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None)
            .with_separators(COMPACT_ITEM_SEPARATOR, COMPACT_KEY_SEPARATOR)
    };
    let encoded: String = dumps(&payload, &JsonDialect::Stdlib(options))?;
    Ok(format!("{:x}", Sha256::digest(encoded.as_bytes())))
}
