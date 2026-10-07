//! The entries of one directory, as `sorted(directory.iterdir())` sees them.

use crate::_helpers::reading::listing_failure;
use crate::models::StageFailure;
use crate::tree::_helpers::listing::join_relative;
use crate::tree::_helpers::ordering::compare_relative_paths;
use crate::tree::_helpers::walking::listing;
use crate::tree::models::{ProjectTree, TreeEntry};

/// `sorted(directory.iterdir())` with relative paths; an unreadable directory fails as in Python.
pub fn children(
    tree: &ProjectTree,
    directory: &str,
) -> Result<Vec<(String, TreeEntry)>, StageFailure> {
    if let Err(error) = std::fs::read_dir(tree.absolute(directory)) {
        return Err(StageFailure::Unlistable {
            relative_path: directory.to_owned(),
            error: listing_failure(&error),
        });
    }
    let mut entries: Vec<(String, TreeEntry)> = listing(tree, directory)?
        .iter()
        .map(|entry| (join_relative(directory, &entry.segment), entry.clone()))
        .collect();
    entries.sort_by(|left, right| compare_relative_paths(&left.0, &right.0));
    Ok(entries)
}
