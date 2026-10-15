//! `get_byte_counts`: the current size of each stream file of one capture.

use std::path::Path;

use crate::compute_logs::_helpers::paths::{ensure_contained, existing_capture};
use crate::compute_logs::constants::STREAM_FILE_NAMES;
use crate::compute_logs::errors::ComputeLogError;

/// Stdout, stderr and diagnostics sizes; a missing stream file counts as empty.
pub fn stream_byte_counts(root: &Path, invocation_id: &str) -> Result<[u64; 3], ComputeLogError> {
    let directory = existing_capture(root, invocation_id)?;
    let mut sizes: [u64; 3] = [0; 3];
    for (size, name) in sizes.iter_mut().zip(STREAM_FILE_NAMES) {
        let path = directory.join(name);
        ensure_contained(root, &path)?;
        if path.exists() {
            *size = std::fs::metadata(&path)?.len();
        }
    }
    Ok(sizes)
}
