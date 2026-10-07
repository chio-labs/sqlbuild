//! Text form of a content digest.

use crate::digest::types::ContentDigest;

/// Lowercase hexadecimal text of a digest.
pub fn hex_digest(digest: &ContentDigest) -> String {
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}
