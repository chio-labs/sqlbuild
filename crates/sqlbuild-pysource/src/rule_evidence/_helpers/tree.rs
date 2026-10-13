//! A parsed module's nodes in `ast.walk` order, each with the index of its parent node.

use ruff_python_ast::Stmt;

use crate::cpython_tree::main::child_nodes::child_nodes;
use crate::cpython_tree::models::CpythonNode;

/// Every node below the module, breadth first; a top-level statement has no parent.
pub(crate) struct NodeTree<'a> {
    pub(crate) nodes: Vec<CpythonNode<'a>>,
    pub(crate) parents: Vec<Option<usize>>,
}

impl<'a> NodeTree<'a> {
    pub(crate) fn new(body: &'a [Stmt]) -> Self {
        let mut nodes: Vec<CpythonNode<'a>> = body.iter().map(CpythonNode::Stmt).collect();
        let mut parents: Vec<Option<usize>> = vec![None; nodes.len()];
        let mut index: usize = 0;
        while index < nodes.len() {
            let children: Vec<CpythonNode<'a>> = child_nodes(&nodes[index]);
            parents.extend(std::iter::repeat_n(Some(index), children.len()));
            nodes.extend(children);
            index += 1;
        }
        Self { nodes, parents }
    }

    pub(crate) fn stmt(&self, index: usize) -> Option<&'a Stmt> {
        match self.nodes[index] {
            CpythonNode::Stmt(statement) => Some(statement),
            _ => None,
        }
    }
}
