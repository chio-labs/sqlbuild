//! The serializer options capture text is written with.

use sqlbuild_core::json::models::{JsonDialect, StdlibJsonOptions};

/// `json.dumps(value, ensure_ascii=False, allow_nan=False, ...)` with `indent` and separators.
pub(crate) fn capture_dialect(indent: Option<usize>, separators: (&str, &str)) -> JsonDialect {
    JsonDialect::Stdlib(StdlibJsonOptions {
        ensure_ascii: false,
        allow_nan: false,
        ..StdlibJsonOptions::new(indent).with_separators(separators.0, separators.1)
    })
}
