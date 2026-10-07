//! Read every listing below a root into the shared snapshot.

use crate::models::StageDeferral;
use crate::tree::_helpers::walking::walk;
use crate::tree::models::ProjectTree;

/// List `root` and every real directory below it; a missing root reads nothing.
pub fn read_tree(tree: &ProjectTree, root: &str) -> Result<(), StageDeferral> {
    if tree.is_dir(root) {
        let _walked = walk(tree, root)?;
    }
    Ok(())
}
