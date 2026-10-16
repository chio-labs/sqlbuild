//! `depth_first_postorder`: nodes after the nodes they lead to, depth first from each root.

use std::collections::HashSet;
use std::hash::Hash;

/// Every node reachable from `roots`, each after its neighbours, visiting roots and neighbours in the given order and entering each node once.
pub fn depth_first_postorder<K, I, N>(
    roots: impl IntoIterator<Item = K>,
    mut neighbours: N,
) -> Vec<K>
where
    K: Clone + Eq + Hash,
    I: IntoIterator<Item = K>,
    N: FnMut(&K) -> I,
{
    let mut pending: Vec<(K, bool)> = roots.into_iter().map(|root| (root, false)).collect();
    pending.reverse();
    let mut entered: HashSet<K> = HashSet::new();
    let mut ordered: Vec<K> = Vec::new();
    while let Some((node, finished)) = pending.pop() {
        if finished {
            ordered.push(node);
            continue;
        }
        if !entered.insert(node.clone()) {
            continue;
        }
        let next: Vec<K> = neighbours(&node).into_iter().collect();
        pending.push((node, true));
        pending.extend(next.into_iter().rev().map(|neighbour| (neighbour, false)));
    }
    ordered
}
