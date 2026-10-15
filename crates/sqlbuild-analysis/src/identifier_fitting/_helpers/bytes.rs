//! UTF-8 byte truncation and short digests.

use sha2::{Digest, Sha256};

use crate::identifier_fitting::constants::SHORTENED_NAME_HASH_LENGTH;

/// The longest prefix whose UTF-8 encoding fits in `max_bytes`, never splitting a character.
pub(crate) fn truncate_bytes(value: &str, max_bytes: usize) -> &str {
    let mut end: usize = max_bytes.min(value.len());
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    &value[..end]
}

/// The first hex digits of the SHA-256 digest of `value`.
pub(crate) fn short_hash(value: &str) -> String {
    let digest: String = format!("{:x}", Sha256::digest(value.as_bytes()));
    digest[..SHORTENED_NAME_HASH_LENGTH].to_owned()
}
