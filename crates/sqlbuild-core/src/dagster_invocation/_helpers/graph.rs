//! Edge sets of a DAG artifact keyed by node position.

use std::collections::{BTreeSet, HashMap};

/// Upstream positions and ordered, distinct downstream positions of each node.
pub(crate) struct EdgeSets {
    pub(crate) incoming: HashMap<usize, BTreeSet<usize>>,
    pub(crate) outgoing: HashMap<usize, Vec<usize>>,
}

/// Edge sets over known nodes; edges naming unknown nodes are ignored.
pub(crate) fn edge_sets(
    unique: &[usize],
    (positions, edges): (&HashMap<&str, usize>, &[(String, String)]),
) -> EdgeSets {
    let mut incoming: HashMap<usize, BTreeSet<usize>> = unique
        .iter()
        .map(|position| (*position, BTreeSet::new()))
        .collect();
    let mut outgoing: HashMap<usize, Vec<usize>> = unique
        .iter()
        .map(|position| (*position, Vec::new()))
        .collect();
    for (from_id, to_id) in edges {
        let (Some(from), Some(to)) = (
            positions.get(from_id.as_str()),
            positions.get(to_id.as_str()),
        ) else {
            continue;
        };
        incoming.entry(*to).or_default().insert(*from);
        let downstream: &mut Vec<usize> = outgoing.entry(*from).or_default();
        if !downstream.contains(to) {
            downstream.push(*to);
        }
    }
    EdgeSets { incoming, outgoing }
}

/// The last position of each distinct id, in first-seen id order, as a dict keyed by id keeps.
pub(crate) fn unique_positions(ids: &[String], positions: &HashMap<&str, usize>) -> Vec<usize> {
    let mut seen: BTreeSet<&str> = BTreeSet::new();
    let mut unique: Vec<usize> = Vec::new();
    for id in ids {
        if seen.insert(id.as_str())
            && let Some(position) = positions.get(id.as_str())
        {
            unique.push(*position);
        }
    }
    unique
}

/// The last position of each id.
pub(crate) fn id_positions(ids: &[String]) -> HashMap<&str, usize> {
    ids.iter()
        .enumerate()
        .map(|(position, id)| (id.as_str(), position))
        .collect()
}
