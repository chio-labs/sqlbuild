//! `decoded_run_cursor`: the `created_at` text and run id a run cursor names.

use serde_json::Value;

use crate::execution_history::_helpers::base64url::decode;
use crate::execution_history::_helpers::dialects::run_cursor_prefix;
use crate::execution_history::constants::{MALFORMED_RUN_CURSOR, RUN_CURSOR_PART_COUNT};
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::{DecodedRunCursor, Dialect};

/// The position of a well-formed run cursor issued by the storage with `namespace`.
pub fn decoded_run_cursor(
    dialect: Dialect,
    cursor: &str,
    namespace: &str,
) -> Result<DecodedRunCursor, HistoryError> {
    let malformed = || HistoryError::new(HistoryErrorKind::InvalidCursor, MALFORMED_RUN_CURSOR);
    let encoded: &str = cursor
        .strip_prefix(run_cursor_prefix(dialect))
        .ok_or_else(malformed)?;
    let bytes: Vec<u8> = decode(encoded).ok_or_else(malformed)?;
    let text: String = String::from_utf8(bytes).map_err(|_| malformed())?;
    let decoded: Value = serde_json::from_str(&text).map_err(|_| malformed())?;
    let Value::Array(parts) = decoded else {
        return Err(malformed());
    };
    let [cursor_namespace, created_at, run_id]: [Value; RUN_CURSOR_PART_COUNT] =
        parts.try_into().map_err(|_| malformed())?;
    let (Value::String(created_at), Value::String(run_id)) = (created_at, run_id) else {
        return Err(malformed());
    };
    if cursor_namespace.as_str() != Some(namespace) || run_id.is_empty() {
        return Err(malformed());
    }
    Ok(DecodedRunCursor {
        created_at_text: created_at,
        run_id,
    })
}
