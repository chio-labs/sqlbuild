//! `find_cycle`: the first cycle a depth-first walk from each root meets.

use std::collections::HashSet;
use std::hash::Hash;

/// The path from a root to the first node met twice on it, ending with that node; finished nodes are shared across roots.
pub fn find_cycle<K, I, N>(roots: impl IntoIterator<Item = K>, mut neighbours: N) -> Option<Vec<K>>
where
    K: Clone + Eq + Hash,
    I: IntoIterator<Item = K>,
    N: FnMut(&K) -> I,
{
    let mut finished: HashSet<K> = HashSet::new();
    for root in roots {
        let mut path: Vec<K> = Vec::new();
        let mut frames: Vec<std::vec::IntoIter<K>> = Vec::new();
        let mut next: Option<K> = Some(root);
        loop {
            if let Some(node) = next.take()
                && !finished.contains(&node)
            {
                if path.contains(&node) {
                    path.push(node);
                    return Some(path);
                }
                frames.push(
                    neighbours(&node)
                        .into_iter()
                        .collect::<Vec<K>>()
                        .into_iter(),
                );
                path.push(node);
            }
            let Some(frame) = frames.last_mut() else {
                break;
            };
            match frame.next() {
                Some(neighbour) => next = Some(neighbour),
                None => {
                    frames.pop();
                    if let Some(done) = path.pop() {
                        finished.insert(done);
                    }
                }
            }
        }
    }
    None
}
