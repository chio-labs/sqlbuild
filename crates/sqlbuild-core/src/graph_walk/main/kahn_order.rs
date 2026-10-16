//! `kahn_order`: nodes in dependency order with Kahn's algorithm and a caller tie-break.

use std::collections::HashMap;
use std::hash::Hash;

use crate::graph_walk::types::ReadyQueue;

/// Take ready nodes from `ready`, seeded with the zero-count `nodes` in order; each successor edge lowers a count once, and nodes left uncounted are never taken.
pub fn kahn_order<K, Q, I, N>(
    (nodes, mut remaining): (impl IntoIterator<Item = K>, HashMap<K, usize>),
    mut ready: Q,
    mut successors: N,
) -> Vec<K>
where
    K: Clone + Eq + Hash,
    Q: ReadyQueue<K>,
    I: IntoIterator<Item = K>,
    N: FnMut(&K) -> I,
{
    for node in nodes {
        if remaining.get(&node) == Some(&0) {
            ready.offer(node);
        }
    }
    let mut ordered: Vec<K> = Vec::with_capacity(remaining.len());
    while let Some(current) = ready.take() {
        for successor in successors(&current) {
            if let Some(count) = remaining.get_mut(&successor)
                && *count > 0
            {
                *count -= 1;
                if *count == 0 {
                    ready.offer(successor);
                }
            }
        }
        ordered.push(current);
    }
    ordered
}
