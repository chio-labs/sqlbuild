//! `inventory`: every complete and abandoned capture beneath the root.

use std::path::Path;

use crate::compute_logs::_helpers::stored::inventory;
use crate::compute_logs::errors::ComputeLogError;
use crate::compute_logs::models::InventoryEntry;

/// Captures ordered by capture date and invocation id.
pub fn capture_inventory(root: &Path) -> Result<Vec<InventoryEntry>, ComputeLogError> {
    inventory(root)
}
