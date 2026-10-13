//! `secret_field_name`: whether a structured logging field holds a secret by its name.

use crate::redaction::constants::SECRET_FIELD_PARTS;

/// Whether the lowercased name, with `-` read as `_`, contains a secret field part.
#[must_use]
pub fn secret_field_name(name: &str) -> bool {
    let lowered: String = name.to_lowercase().replace('-', "_");
    SECRET_FIELD_PARTS.iter().any(|part| lowered.contains(part))
}
