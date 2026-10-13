//! CPython's `ast.iter_child_nodes` over mirrored nodes.

use crate::cpython_tree::_helpers::children::children;
use crate::cpython_tree::models::CpythonNode;

/// The children of `node` that can hold other nodes, in CPython's `_fields` order.
pub(crate) fn child_nodes<'a>(node: &CpythonNode<'a>) -> Vec<CpythonNode<'a>> {
    children(node)
}
