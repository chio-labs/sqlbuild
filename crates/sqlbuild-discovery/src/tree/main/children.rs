//! The entries of one directory, as `sorted(directory.iterdir())` sees them.

use crate::models::StageDeferral;
use crate::tree::_helpers::listing::join_relative;
use crate::tree::_helpers::ordering::compare_relative_paths;
use crate::tree::_helpers::walking::listing;
use crate::tree::models::{ProjectTree, TreeEntry};

/// `sorted(directory.iterdir())` with relative paths; an unreadable directory defers.
pub fn children(
    tree: &ProjectTree,
    directory: &str,
) -> Result<Vec<(String, TreeEntry)>, StageDeferral> {
    if let Err(error) = std::fs::read_dir(tree.absolute(directory)) {
        return Err(StageDeferral {
            reason: format!("cannot list {directory}: {error}"),
        });
    }
    let mut entries: Vec<(String, TreeEntry)> = listing(tree, directory)?
        .iter()
        .map(|entry| (join_relative(directory, &entry.name), entry.clone()))
        .collect();
    entries.sort_by(|left, right| compare_relative_paths(&left.0, &right.0));
    Ok(entries)
}
