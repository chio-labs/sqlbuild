//! The key unordered capture items are sorted by.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::stage_capture::_helpers::noise::masked;

/// `mask_capture_noise(json.dumps(item, sort_keys=True, ensure_ascii=False))`.
pub fn capture_sort_key(item: &JsonValue) -> Result<String, JsonEmitError> {
    let dialect: JsonDialect = JsonDialect::Stdlib(StdlibJsonOptions {
        ensure_ascii: false,
        sort_keys: true,
        ..StdlibJsonOptions::new(None)
    });
    Ok(masked(&dumps(item, &dialect)?))
}
