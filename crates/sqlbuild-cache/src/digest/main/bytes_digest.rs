//! The BLAKE3 digest of bytes held in memory, equal to `digest_files` for the same contents.

use crate::digest::types::ContentDigest;

/// The digest `digest_files` gives a file holding exactly `contents`.
pub fn bytes_digest(contents: &[u8]) -> ContentDigest {
    *blake3::hash(contents).as_bytes()
}
