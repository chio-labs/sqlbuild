//! The JSON text a stored macro call key is built from.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// Compact unescaped JSON of `value`; `None` when a lone surrogate leaves it unstorable.
pub(crate) fn key_text(value: &JsonValue) -> Result<Option<String>, JsonEmitError> {
    let dialect: JsonDialect = JsonDialect::Stdlib(StdlibJsonOptions {
        ensure_ascii: false,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    });
    match dumps(value, &dialect) {
        Ok(text) => Ok(Some(text)),
        Err(JsonEmitError::LoneSurrogate) => Ok(None),
        Err(error) => Err(error),
    }
}
