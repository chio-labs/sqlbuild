use std::path::Path;

use crate::project_reuse::models::{DeltaBase, StoredOutput};

/// The stored compile at `store_path` with its image, the base a delta compile patches.
pub fn read_delta_base(store_path: &Path) -> Option<DeltaBase> {
    crate::project_reuse::_helpers::entry::read_delta_base(store_path)
}

/// The output of the stored compile `base` was read from, or `None` when it no longer is.
pub fn read_delta_output(store_path: &Path, base: &DeltaBase) -> Option<StoredOutput> {
    crate::project_reuse::_helpers::entry::read_delta_output(store_path, base)
}
