//! `sorted(root.rglob(pattern))` over the shared snapshot.

use crate::models::StageFailure;
use crate::tree::_helpers::listing::join_relative;
use crate::tree::_helpers::ordering::compare_relative_paths;
use crate::tree::_helpers::walking::{WalkedDirectory, walk};
use crate::tree::models::{ProjectTree, TreeEntry};

/// Every entry below `root` that `accept` keeps, in Python's sorted path order.
pub fn rglob(
    tree: &ProjectTree,
    root: &str,
    accept: impl Fn(&TreeEntry) -> bool,
) -> Result<Vec<String>, StageFailure> {
    if !tree.is_dir(root) {
        return Ok(Vec::new());
    }
    let mut selected: Vec<String> = Vec::new();
    for walked in walk(tree, root)? {
        selected.extend(accepted_paths(&walked, &accept));
    }
    selected.sort_by(|left, right| compare_relative_paths(left, right));
    Ok(selected)
}

fn accepted_paths(walked: &WalkedDirectory, accept: &impl Fn(&TreeEntry) -> bool) -> Vec<String> {
    let (directory, listing) = walked;
    listing
        .iter()
        .filter(|entry| accept(entry))
        .map(|entry| join_relative(directory, &entry.segment))
        .collect()
}
