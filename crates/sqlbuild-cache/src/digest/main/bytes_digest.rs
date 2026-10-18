//! The BLAKE3 digest of bytes held in memory, equal to `digest_files` for the same contents.

use crate::digest::constants::PARALLEL_HASH_BYTES;
use crate::digest::types::ContentDigest;

/// The digest `digest_files` gives a file holding exactly `contents`.
pub fn bytes_digest(contents: &[u8]) -> ContentDigest {
    if contents.len() < PARALLEL_HASH_BYTES {
        return *blake3::hash(contents).as_bytes();
    }
    let mut hasher: blake3::Hasher = blake3::Hasher::new();
    let _ = hasher.update_rayon(contents);
    *hasher.finalize().as_bytes()
}
