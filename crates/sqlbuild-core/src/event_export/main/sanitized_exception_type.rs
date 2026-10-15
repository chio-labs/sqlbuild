//! Bounded, low-cardinality exception class names safe for exporter health diagnostics.

use crate::event_export::constants::{FALLBACK_EXCEPTION_TYPE, MAX_EXCEPTION_TYPE_LENGTH};

/// `name` with every character outside `[A-Za-z0-9_]` replaced by `_`, truncated to 100 characters.
#[must_use]
pub fn sanitized_exception_type(name: &str) -> String {
    let sanitized: String = name
        .chars()
        .take(MAX_EXCEPTION_TYPE_LENGTH)
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' {
                character
            } else {
                '_'
            }
        })
        .collect();
    if sanitized.is_empty() {
        FALLBACK_EXCEPTION_TYPE.to_owned()
    } else {
        sanitized
    }
}
