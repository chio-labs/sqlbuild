//! Caller-supplied tree behaviour.

use crate::lineage_graph::models::TreeLine;

/// The caller's view of a tree: node identity, child order and line output.
pub trait TreeVisitor<N, K, E> {
    /// The identity a node is shown once by.
    fn key(&mut self, node: &N) -> Result<K, E>;
    /// Record one line.
    fn line(&mut self, line: TreeLine<'_, N>) -> Result<(), E>;
    /// A node's children, in display order.
    fn children(&mut self, node: &N) -> Result<Vec<N>, E>;
}
