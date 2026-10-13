//! Box-drawing tree traversal that expands each node once across the tree.

use std::collections::HashSet;
use std::hash::Hash;

use crate::lineage_graph::constants::{
    TREE_BRANCH_LAST, TREE_BRANCH_MID, TREE_CONTINUATION_LAST, TREE_CONTINUATION_MID,
};
use crate::lineage_graph::models::TreeLine;
use crate::lineage_graph::types::TreeVisitor;

/// Visit `children` depth first in order, emitting one line per node; repeats are not expanded.
pub fn tree_lines<N, K, E>(
    children: Vec<N>,
    seen: HashSet<K>,
    visitor: &mut impl TreeVisitor<N, K, E>,
) -> Result<(), E>
where
    K: Eq + Hash,
{
    let mut shown: HashSet<K> = seen;
    let mut pending: Vec<(N, String, bool)> = pending_children(children, "");
    while let Some((node, prefix, is_last)) = pending.pop() {
        let key: K = visitor.key(&node)?;
        let repeated: bool = shown.contains(&key);
        visitor.line(TreeLine {
            node: &node,
            prefix: &prefix,
            branch: if is_last {
                TREE_BRANCH_LAST
            } else {
                TREE_BRANCH_MID
            },
            repeated,
        })?;
        if repeated {
            continue;
        }
        let _ = shown.insert(key);
        let continuation: &str = if is_last {
            TREE_CONTINUATION_LAST
        } else {
            TREE_CONTINUATION_MID
        };
        let grandchildren: Vec<N> = visitor.children(&node)?;
        pending.extend(pending_children(
            grandchildren,
            &format!("{prefix}{continuation}"),
        ));
    }
    Ok(())
}

fn pending_children<N>(children: Vec<N>, prefix: &str) -> Vec<(N, String, bool)> {
    let last: usize = children.len().saturating_sub(1);
    let mut pending: Vec<(N, String, bool)> = children
        .into_iter()
        .enumerate()
        .map(|(index, child)| (child, prefix.to_owned(), index == last))
        .collect();
    pending.reverse();
    pending
}
