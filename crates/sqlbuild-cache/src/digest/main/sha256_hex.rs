//! The SHA-256 text Python's `hashlib.sha256(data).hexdigest()` gives.

use sha2::{Digest, Sha256};

/// Lowercase hexadecimal SHA-256 of `bytes`.
#[must_use]
pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
