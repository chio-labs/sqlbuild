//! `prune`: keep the newest complete captures under the prune file lock.

use std::path::Path;

use crate::compute_logs::_helpers::paths::{ensure_contained, ensure_not_symlink};
use crate::compute_logs::_helpers::prune::{acquire_lock, release_lock};
use crate::compute_logs::_helpers::stored::{delete_inactive, inventory};
use crate::compute_logs::constants::COMPLETE_FILE_NAME;
use crate::compute_logs::errors::ComputeLogError;
use crate::compute_logs::models::{InventoryEntry, PruneOutcome};

fn completion_key(entry: &InventoryEntry) -> (i64, &str) {
    let instant = entry
        .document
        .completion
        .as_ref()
        .map_or(entry.document.started_at.micros, |completion| {
            completion.completed_at.micros
        });
    (instant, entry.document.invocation_id.as_str())
}

/// Delete all but `retain` complete captures, newest kept; incomplete captures always stay.
pub fn prune_captures(
    root: &Path,
    retain: Option<usize>,
    is_active: &dyn Fn(&str) -> bool,
) -> Result<PruneOutcome, ComputeLogError> {
    let Some(retain) = retain else {
        let captures = inventory(root)?;
        let complete = captures.iter().filter(|entry| entry.is_complete).count();
        return Ok(PruneOutcome {
            deleted_invocation_ids: Vec::new(),
            retained_complete_count: complete,
            retained_incomplete_count: captures.len() - complete,
        });
    };
    let lock = acquire_lock(root)?;
    let result = prune_locked(root, retain, is_active);
    release_lock(root, lock);
    result
}

fn prune_locked(
    root: &Path,
    retain: usize,
    is_active: &dyn Fn(&str) -> bool,
) -> Result<PruneOutcome, ComputeLogError> {
    let captures = inventory(root)?;
    let incomplete = captures.iter().filter(|entry| !entry.is_complete).count();
    let mut complete: Vec<&InventoryEntry> =
        captures.iter().filter(|entry| entry.is_complete).collect();
    complete.sort_by(|left, right| completion_key(right).cmp(&completion_key(left)));
    let mut deleted: Vec<String> = Vec::new();
    for entry in complete.iter().skip(retain) {
        ensure_not_symlink(&entry.path)?;
        ensure_contained(root, &entry.path)?;
        let marker = entry.path.join(COMPLETE_FILE_NAME);
        ensure_contained(root, &marker)?;
        if !marker.is_file() {
            continue;
        }
        let invocation_id = entry.document.invocation_id.as_str();
        delete_inactive(root, invocation_id, is_active(invocation_id))?;
        deleted.push(invocation_id.to_owned());
    }
    Ok(PruneOutcome {
        retained_complete_count: complete.len() - deleted.len(),
        deleted_invocation_ids: deleted,
        retained_incomplete_count: incomplete,
    })
}
