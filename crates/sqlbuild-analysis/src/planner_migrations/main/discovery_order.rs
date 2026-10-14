//! Stable depth-first ordering for migration identity propagation.

use std::collections::{BTreeMap, BTreeSet};

/// Order models after their model dependencies using lexical traversal ties.
pub fn discovery_order(dependencies: &BTreeMap<String, Vec<String>>) -> Vec<String> {
    let mut pending: Vec<(String, bool)> = dependencies
        .keys()
        .rev()
        .map(|name| (name.clone(), false))
        .collect();
    let mut visited: BTreeSet<String> = BTreeSet::new();
    let mut ordered: Vec<String> = Vec::new();
    while let Some((name, expanded)) = pending.pop() {
        if expanded {
            ordered.push(name);
            continue;
        }
        if !visited.insert(name.clone()) {
            continue;
        }
        pending.push((name.clone(), true));
        let mut upstream = dependencies[&name].clone();
        upstream.sort();
        pending.extend(upstream.into_iter().rev().filter_map(|dependency| {
            (dependencies.contains_key(&dependency) && !visited.contains(&dependency))
                .then_some((dependency, false))
        }));
    }
    ordered
}
