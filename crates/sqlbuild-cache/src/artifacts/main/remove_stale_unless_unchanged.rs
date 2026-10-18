use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::artifacts::_helpers::files::remove_stale_listing;
use crate::artifacts::_helpers::tree_stamp::{
    forget_tree, managed_digest, now_ns, record_tree, tree_unchanged,
};
use crate::artifacts::errors::ArtifactError;
use crate::digest::types::ContentDigest;

/// `remove_stale`, skipped while the tree stamped at `stamp_path` still holds exactly `managed`.
pub fn remove_stale_unless_unchanged(
    compiled_dir: &Path,
    managed: &HashSet<PathBuf>,
    stamp_path: &Path,
    racy_window_ns: i64,
) -> Result<usize, ArtifactError> {
    let digest: ContentDigest = managed_digest(compiled_dir, managed);
    if tree_unchanged(stamp_path, &digest) {
        return Ok(0);
    }
    forget_tree(stamp_path);
    let trusted_ns: i64 = now_ns().saturating_sub(racy_window_ns);
    let (removed, folders) = remove_stale_listing(compiled_dir, managed)?;
    if let Some(folders) = folders {
        record_tree(stamp_path, &digest, &folders, trusted_ns);
    }
    Ok(removed)
}
