use std::path::Path;

use crate::project_reuse::models::{DeltaBase, StoredOutput};

/// The output of the stored compile `base` was read from, or `None` when it no longer is.
pub fn read_delta_output(store_path: &Path, base: &DeltaBase) -> Option<StoredOutput> {
    crate::project_reuse::_helpers::entry::read_delta_output(store_path, base)
}
