//! BLAKE3 over length-prefixed fields, so no two field lists share a key.

use crate::constants::NATIVE_BUILD_IDENTITY;
use crate::rule_cache::constants::CACHE_VERSION;

/// The hex digest of the cache version, the native build and each field in order.
pub(crate) fn field_digest(kind: &str, fields: &[&str]) -> String {
    let mut digest = blake3::Hasher::new();
    for field in [CACHE_VERSION, NATIVE_BUILD_IDENTITY, kind]
        .iter()
        .chain(fields.iter())
    {
        digest.update(&(field.len() as u64).to_le_bytes());
        digest.update(field.as_bytes());
    }
    digest.finalize().to_hex().to_string()
}
