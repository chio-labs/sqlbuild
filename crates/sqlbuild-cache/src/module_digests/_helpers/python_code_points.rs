//! The code points of a Python `str`, the order Python compares strings in.

use sqlbuild_core::json::models::JsonValue;

/// The code points of a JSON string, a lone surrogate as its own value; empty for other values.
pub(crate) fn python_code_points(value: &JsonValue) -> Vec<u32> {
    match value {
        JsonValue::String(text) => text.chars().map(u32::from).collect(),
        JsonValue::Utf16(units) => char::decode_utf16(units.iter().copied())
            .map(|unit| unit.map_or_else(|lone| u32::from(lone.unpaired_surrogate()), u32::from))
            .collect(),
        _ => Vec::new(),
    }
}
