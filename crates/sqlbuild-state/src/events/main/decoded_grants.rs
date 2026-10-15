//! `decoded_grants`: stored grant text back to the copied statements.

use serde_json::Value;

use crate::events::_helpers::python_text::python_text;

/// The statements of a stored JSON array; absent, invalid or non-array text reads as unknown.
#[must_use]
pub fn decoded_grants(raw: Option<&str>) -> Option<Vec<String>> {
    match serde_json::from_str::<Value>(raw?) {
        Ok(Value::Array(statements)) => Some(statements.iter().map(python_text).collect()),
        _ => None,
    }
}
