//! The digest of definition parts.

use sha2::{Digest, Sha256};

/// The SHA-256 hex digest of `parts`, each length-prefixed so boundaries cannot shift.
pub fn definition_digest(parts: &[&str]) -> String {
    let mut digest = Sha256::new();
    for part in parts {
        digest.update(part.len().to_string().as_bytes());
        digest.update(b":");
        digest.update(part.as_bytes());
    }
    format!("{:x}", digest.finalize())
}
