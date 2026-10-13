//! Every node upstream of one Python node, sorted.

use std::collections::{HashMap, HashSet, VecDeque};

/// `sorted(transitive_closure(start=start, edges=upstream))`: `start` only when on a cycle.
pub fn upstream_closure(start: &str, upstream: &HashMap<String, Vec<String>>) -> Vec<String> {
    let mut visited: HashSet<&str> = HashSet::new();
    let mut frontier: VecDeque<&str> = VecDeque::from([start]);
    while let Some(current) = frontier.pop_front() {
        for neighbor in upstream.get(current).into_iter().flatten() {
            if visited.insert(neighbor) {
                frontier.push_back(neighbor);
            }
        }
    }
    let mut names: Vec<String> = visited.into_iter().map(str::to_owned).collect();
    names.sort();
    names
}
