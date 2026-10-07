//! `sorted(path for path in DirectorySnapshot.directories(root))` over the shared snapshot.

use crate::models::StageFailure;
use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;

/// Every directory below `root`, including unwalked directory links, in Python's path order.
pub fn directories(tree: &ProjectTree, root: &str) -> Result<Vec<String>, StageFailure> {
    rglob(tree, root, |entry| entry.is_dir)
}
