//! Reject capture identities that are unsafe as local directory names.

use crate::compute_logs::_helpers::paths;
use crate::compute_logs::errors::ComputeLogError;

/// Python's `[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z` capture identity.
pub fn validate_capture_id(invocation_id: &str) -> Result<(), ComputeLogError> {
    paths::validate_capture_id(invocation_id)
}
