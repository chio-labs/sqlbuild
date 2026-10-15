//! `decoded_column_aliases`: stored column alias text back to sorted pairs.

use serde_json::Value;

use crate::events::_helpers::python_text::python_text;

/// Sorted `(old, new)` pairs of a stored JSON object; empty, invalid or non-object text reads as none.
#[must_use]
pub fn decoded_column_aliases(raw: Option<&str>) -> Vec<(String, String)> {
    let Some(raw) = raw.filter(|raw| !raw.is_empty()) else {
        return Vec::new();
    };
    let Ok(Value::Object(mapping)) = serde_json::from_str::<Value>(raw) else {
        return Vec::new();
    };
    let mut pairs: Vec<(String, String)> = mapping
        .iter()
        .map(|(old, new)| (old.clone(), python_text(new)))
        .collect();
    pairs.sort();
    pairs
}
