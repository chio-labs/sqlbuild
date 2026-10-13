//! The compact JSON text a capture subtree is shared and digested as.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::JsonValue;

use crate::stage_capture::_helpers::dialect::capture_dialect;

/// `json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))`.
pub fn compact_capture_json(value: &JsonValue) -> Result<String, JsonEmitError> {
    dumps(value, &capture_dialect(None, (",", ":")))
}
