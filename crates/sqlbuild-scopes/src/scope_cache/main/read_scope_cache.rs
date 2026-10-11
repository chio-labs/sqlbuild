//! `read_cached_scope_index`: every storage or validation fault is a miss.

use std::path::Path;

use crate::scope_cache::_helpers::decode::decode_envelope;
use crate::scope_cache::constants::CACHE_MAX_BYTES;
use crate::scope_cache::models::{CacheMiss, CachedIndex};

/// The verified cached index at `path` for `fingerprint`, else why it is a miss.
pub fn read_scope_cache(path: &Path, fingerprint: &str) -> Result<CachedIndex, CacheMiss> {
    let size: u64 = std::fs::metadata(path)
        .map_err(|_| CacheMiss::Unreadable)?
        .len();
    if size > CACHE_MAX_BYTES {
        return Err(CacheMiss::Unreadable);
    }
    let raw: Vec<u8> = std::fs::read(path).map_err(|_| CacheMiss::Unreadable)?;
    decode_envelope(&raw, fingerprint)
}
