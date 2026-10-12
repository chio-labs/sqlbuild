//! CPython's `ast.walk` order over mirrored nodes.

use std::collections::VecDeque;

use crate::cpython_tree::_helpers::children::children;
use crate::cpython_tree::models::CpythonNode;

/// `roots` and every node below them, breadth first with children in CPython's `_fields` order.
pub(crate) fn walk_breadth_first<'a>(roots: Vec<CpythonNode<'a>>) -> Vec<CpythonNode<'a>> {
    let mut queue: VecDeque<CpythonNode<'a>> = VecDeque::from(roots);
    let mut visited: Vec<CpythonNode<'a>> = Vec::new();
    while let Some(node) = queue.pop_front() {
        queue.extend(children(&node));
        visited.push(node);
    }
    visited
}
