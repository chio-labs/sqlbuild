//! Visited-node sets and ready queues the graph walks are generic over.

/// A set of graph nodes a walk records and queries, possibly through a fallible host.
pub trait NodeSet<K> {
    /// The failure a fallible set or its walk's neighbour lookup reports.
    type Error;
    /// Record `key`, returning whether it was absent.
    fn insert_new(&mut self, key: &K) -> Result<bool, Self::Error>;
    /// Whether `key` is recorded.
    fn holds(&self, key: &K) -> Result<bool, Self::Error>;
}

/// Nodes a topological walk may take next, in the caller's tie-break order.
pub trait ReadyQueue<K> {
    /// Offer a node whose dependencies are all taken.
    fn offer(&mut self, key: K);
    /// The next node to take.
    fn take(&mut self) -> Option<K>;
}
