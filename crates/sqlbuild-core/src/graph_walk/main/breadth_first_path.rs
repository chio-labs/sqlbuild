//! `breadth_first_path`: the shortest path from a node to the first goal it reaches.

use std::collections::{HashSet, VecDeque};
use std::hash::Hash;

/// The shortest path from `origin` ending at a goal neighbour, entering only nodes `enter` allows; the origin itself is never re-entered.
pub fn breadth_first_path<K, I, N, G, E>(
    origin: K,
    (mut neighbours, is_goal, enter): (N, G, E),
) -> Option<Vec<K>>
where
    K: Clone + Eq + Hash,
    I: IntoIterator<Item = K>,
    N: FnMut(&K) -> I,
    G: Fn(&K) -> bool,
    E: Fn(&K) -> bool,
{
    let mut visited: HashSet<K> = HashSet::from([origin.clone()]);
    let mut pending: VecDeque<Vec<K>> = VecDeque::from([vec![origin]]);
    while let Some(path) = pending.pop_front() {
        let last: &K = path.last()?;
        for neighbour in neighbours(last) {
            let mut candidate: Vec<K> = path.clone();
            candidate.push(neighbour.clone());
            if is_goal(&neighbour) {
                return Some(candidate);
            }
            if enter(&neighbour) && visited.insert(neighbour) {
                pending.push_back(candidate);
            }
        }
    }
    None
}
