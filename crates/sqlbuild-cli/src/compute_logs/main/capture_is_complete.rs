//! `is_complete`: whether a capture's completion marker exists.

use std::path::Path;

use crate::compute_logs::_helpers::paths::{ensure_contained, existing_capture};
use crate::compute_logs::constants::COMPLETE_FILE_NAME;
use crate::compute_logs::errors::ComputeLogError;

/// Capture-close evidence, without asserting the command's lifecycle status.
pub fn capture_is_complete(root: &Path, invocation_id: &str) -> Result<bool, ComputeLogError> {
    let marker = existing_capture(root, invocation_id)?.join(COMPLETE_FILE_NAME);
    ensure_contained(root, &marker)?;
    Ok(marker.is_file())
}
