use std::path::Path;

use crate::project_reuse::models::DeltaBase;

/// The stored compile at `store_path` with its image, the base a delta compile patches.
pub fn read_delta_base(store_path: &Path) -> Option<DeltaBase> {
    crate::project_reuse::_helpers::entry::read_delta_base(store_path)
}
