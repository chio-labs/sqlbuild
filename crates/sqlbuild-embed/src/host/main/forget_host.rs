//! Drop a cached discovery that turned out not to load.

use std::path::Path;

use crate::host::_helpers::cache::forget_cached;

/// Forget what the cache under `cache_root` says about `interpreter`, so the next run looks again.
pub fn forget_host(cache_root: Option<&Path>, interpreter: &Path) {
    if let Some(root) = cache_root {
        forget_cached(root, interpreter);
    }
}
