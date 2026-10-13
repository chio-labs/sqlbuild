//! The text a canonical set member is ordered by.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// `json.dumps(item, sort_keys=True)`.
pub fn canonical_sort_text(item: &JsonValue) -> Result<String, JsonEmitError> {
    dumps(
        item,
        &JsonDialect::Stdlib(StdlibJsonOptions {
            sort_keys: true,
            ..StdlibJsonOptions::new(None)
        }),
    )
}
