//! The JSON text a stored macro call key is built from.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// `json.dumps(value, ensure_ascii=False, separators=(",", ":"))`, or `None` when the text
/// holds a lone surrogate, which the native store cannot encode.
pub(crate) fn key_text(value: &JsonValue) -> Option<String> {
    let dialect: JsonDialect = JsonDialect::Stdlib(StdlibJsonOptions {
        ensure_ascii: false,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    });
    dumps(value, &dialect).ok()
}
