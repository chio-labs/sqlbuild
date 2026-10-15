//! `delete`: remove one complete, inactive capture.

use std::path::Path;

use crate::compute_logs::_helpers::stored::delete_inactive;
use crate::compute_logs::errors::ComputeLogError;

/// Delete the capture; `active` captures and incomplete ones are refused.
pub fn delete_capture(
    root: &Path,
    invocation_id: &str,
    active: bool,
) -> Result<(), ComputeLogError> {
    delete_inactive(root, invocation_id, active)
}
