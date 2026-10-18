use std::path::Path;

use crate::project_reuse::models::{ImageSections, StoredInputs, StoredOutput};

/// The stored compile at `store_path` with its image, the base a delta compile patches.
pub fn read_delta_base(store_path: &Path) -> Option<(StoredInputs, StoredOutput, ImageSections)> {
    crate::project_reuse::_helpers::entry::read_delta_base(store_path)
}
