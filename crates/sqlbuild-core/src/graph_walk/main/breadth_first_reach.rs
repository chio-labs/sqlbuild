//! `breadth_first_reach`: record every node reachable from the starts, breadth first.

use std::collections::VecDeque;

use crate::graph_walk::types::NodeSet;

/// Record nodes within `max_depth` edges of a start in first-visit order; a start counts only when reached, so callers including starts record them first.
pub fn breadth_first_reach<K, S, I, N>(
    starts: impl IntoIterator<Item = K>,
    max_depth: Option<u64>,
    visited: &mut S,
    mut neighbours: N,
) -> Result<(), S::Error>
where
    S: NodeSet<K>,
    I: IntoIterator<Item = K>,
    N: FnMut(&K) -> Result<I, S::Error>,
{
    let mut frontier: VecDeque<(K, u64)> = starts.into_iter().map(|start| (start, 0)).collect();
    while let Some((current, depth)) = frontier.pop_front() {
        if max_depth.is_some_and(|maximum| depth >= maximum) {
            continue;
        }
        for neighbour in neighbours(&current)? {
            if visited.insert_new(&neighbour)? {
                frontier.push_back((neighbour, depth + 1));
            }
        }
    }
    Ok(())
}
