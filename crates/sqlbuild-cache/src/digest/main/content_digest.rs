//! The one digest every native cache key is built from.

use sha2::{Digest, Sha256};

use crate::digest::types::ContentDigest;

/// Digest `parts` with each part length-prefixed, so part boundaries cannot shift.
pub fn content_digest<T: AsRef<[u8]>>(parts: &[T]) -> ContentDigest {
    let mut hasher: Sha256 = Sha256::new();
    for part in parts {
        let bytes: &[u8] = part.as_ref();
        hasher.update((bytes.len() as u64).to_le_bytes());
        hasher.update(bytes);
    }
    hasher.finalize().into()
}
