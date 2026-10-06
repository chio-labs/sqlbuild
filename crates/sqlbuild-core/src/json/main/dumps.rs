//! Serialize JSON exactly as SQLBuild's Python serializers do.

use crate::json::errors::JsonEmitError;
use crate::json::models::{JsonDialect, JsonValue};

/// The text `json.dumps(value, ...)` or `orjson.dumps(value, ...).decode()` returns.
pub fn dumps(value: &JsonValue, dialect: &JsonDialect) -> Result<String, JsonEmitError> {
    crate::json::_helpers::emitter::emit(value, dialect)
}
