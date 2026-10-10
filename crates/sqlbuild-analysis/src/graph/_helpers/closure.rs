//! Python's breadth-first transitive closure and directed path nodes over graph edges.

use std::collections::{BTreeSet, HashSet, VecDeque};

use crate::assembly::project::types::ObjectKey;
use crate::graph::models::{EdgeDirection as Direction, ProjectGraph};

impl ProjectGraph {
    pub(crate) fn edges(&self, key: &ObjectKey, direction: Direction) -> &[ObjectKey] {
        let (entries, index) = match direction {
            Direction::Upstream => (&self.upstream, &self.upstream_index),
            Direction::Downstream => (&self.downstream, &self.downstream_index),
        };
        index
            .get(key)
            .map_or(&[], |&position| entries[position].1.as_slice())
    }

    /// Every key reachable from `start`; `start` itself only through a cycle.
    pub(crate) fn closure(&self, start: &ObjectKey, direction: Direction) -> BTreeSet<ObjectKey> {
        let mut visited: HashSet<&ObjectKey> = HashSet::new();
        let mut frontier: VecDeque<&ObjectKey> = VecDeque::from([start]);
        while let Some(current) = frontier.pop_front() {
            for neighbor in self.edges(current, direction) {
                if visited.insert(neighbor) {
                    frontier.push_back(neighbor);
                }
            }
        }
        visited.into_iter().cloned().collect()
    }

    /// Keys on directed paths from `start` to `end`, or `None` when `end` is not downstream.
    pub(crate) fn path_nodes(
        &self,
        start: &ObjectKey,
        end: &ObjectKey,
    ) -> Option<BTreeSet<ObjectKey>> {
        let reachable: BTreeSet<ObjectKey> = self.closure(start, Direction::Downstream);
        if !reachable.contains(end) {
            return None;
        }
        let mut upstream_of_end: BTreeSet<ObjectKey> = BTreeSet::new();
        let mut stack: Vec<ObjectKey> = vec![end.clone()];
        while let Some(current) = stack.pop() {
            if !upstream_of_end.insert(current.clone()) {
                continue;
            }
            for parent in self.downstream_parents(&current) {
                if reachable.contains(&parent) || &parent == start {
                    stack.push(parent);
                }
            }
        }
        let mut nodes: BTreeSet<ObjectKey> =
            reachable.intersection(&upstream_of_end).cloned().collect();
        nodes.insert(start.clone());
        nodes.insert(end.clone());
        Some(nodes)
    }

    /// Keys whose downstream list holds `key`: the inverse of the downstream edges.
    fn downstream_parents(&self, key: &ObjectKey) -> Vec<ObjectKey> {
        self.downstream
            .iter()
            .filter(|(_, children)| children.contains(key))
            .map(|(parent, _)| parent.clone())
            .collect()
    }
}
