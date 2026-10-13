//! The digest a shared capture subtree is keyed by.

use sha2::{Digest, Sha256};

use crate::stage_capture::_helpers::noise::masked;

/// SHA-256 hex digest of the subtree's compact JSON with its noise masked.
pub fn shared_node_digest(text: &str) -> String {
    Sha256::digest(masked(text).as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
