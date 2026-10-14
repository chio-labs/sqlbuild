//! Stable scenario artifact identity hashing.

use sha2::{Digest, Sha256};

/// Hash a project, optional namespace and scenario without changing the stored identity format.
pub fn hash_prefix(
    project: &str,
    scenario: &str,
    namespace: Option<&str>,
    length: usize,
) -> String {
    let input = namespace.map_or_else(
        || format!("{project}:{scenario}"),
        |namespace| format!("{project}:{namespace}:{scenario}"),
    );
    let hash = format!("{:x}", Sha256::digest(input.as_bytes()));
    hash[..length.min(hash.len())].to_owned()
}
