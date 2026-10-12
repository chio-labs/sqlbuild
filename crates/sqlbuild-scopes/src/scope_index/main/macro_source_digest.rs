//! The source digest of a loaded macro.

use sha2::{Digest, Sha256};

/// Lowercase hex SHA-256 of the UTF-8 macro source, as Python's `hashlib` gives it.
#[must_use]
pub fn macro_source_digest(source: &str) -> String {
    Sha256::digest(source.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
