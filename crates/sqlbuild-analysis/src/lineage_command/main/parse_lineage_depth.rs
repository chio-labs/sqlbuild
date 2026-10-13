//! `--depth`: a non-negative integer, or `all` for unlimited traversal.

use crate::lineage_command::constants::{DEPTH_MESSAGE, UNLIMITED_DEPTH_VALUE};
use crate::lineage_command::errors::LineageError;

/// The depth limit, or `None` for `all`.
pub fn parse_lineage_depth(raw: &str) -> Result<Option<i64>, LineageError> {
    if raw == UNLIMITED_DEPTH_VALUE {
        return Ok(None);
    }
    match raw.trim().parse::<i64>() {
        Ok(depth) if depth >= 0 => Ok(Some(depth)),
        _ => Err(LineageError::new("C304", DEPTH_MESSAGE)),
    }
}
