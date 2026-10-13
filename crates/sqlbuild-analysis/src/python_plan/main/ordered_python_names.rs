//! `_ordered_python_names`: selected Python nodes in dependency order, ties by name.

use std::collections::{BTreeSet, HashMap, HashSet};

/// `selected` ordered so each node follows its selected upstreams; nodes on a cycle are left out.
pub fn ordered_python_names(
    selected: &[String],
    upstream: &HashMap<String, Vec<String>>,
) -> Vec<String> {
    let chosen: HashSet<&str> = selected.iter().map(String::as_str).collect();
    let mut in_degree: HashMap<&str, usize> = HashMap::new();
    let mut downstream: HashMap<&str, Vec<&str>> = HashMap::new();
    for name in &chosen {
        let upstreams: Vec<&str> = upstream
            .get(*name)
            .into_iter()
            .flatten()
            .map(String::as_str)
            .filter(|upstream_name| chosen.contains(upstream_name))
            .collect();
        in_degree.insert(name, upstreams.len());
        for upstream_name in upstreams {
            downstream.entry(upstream_name).or_default().push(name);
        }
    }
    let mut ready: BTreeSet<&str> = in_degree
        .iter()
        .filter(|(_, degree)| **degree == 0)
        .map(|(name, _)| *name)
        .collect();
    let mut ordered: Vec<String> = Vec::new();
    while let Some(name) = ready.pop_first() {
        ordered.push(name.to_owned());
        for downstream_name in downstream.get(name).into_iter().flatten() {
            if let Some(degree) = in_degree.get_mut(downstream_name) {
                *degree -= 1;
                if *degree == 0 {
                    ready.insert(downstream_name);
                }
            }
        }
    }
    ordered
}
