//! Digests binding stored fingerprint cache payloads to their keys.

use sha2::{Digest, Sha256};

/// SHA-256 of the cache key, a NUL byte and the serialized payload.
pub(crate) fn entry_digest(cache_key: &str, serialized: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(cache_key.as_bytes());
    digest.update(b"\0");
    digest.update(serialized.as_bytes());
    format!("{:x}", digest.finalize())
}
