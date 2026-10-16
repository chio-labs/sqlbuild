//! Transitive closure and directed path nodes over project graph edges.

use std::collections::{BTreeSet, HashSet};
use std::convert::Infallible;

use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;
use sqlbuild_core::graph_walk::main::directed_path_nodes::directed_path_nodes;

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
        let Ok(()) = breadth_first_reach([start], None, &mut visited, |current| {
            Ok::<_, Infallible>(self.edges(current, direction))
        });
        visited.into_iter().cloned().collect()
    }

    /// Keys on directed paths from `start` to `end`, or `None` when `end` is not downstream.
    pub(crate) fn path_nodes(
        &self,
        start: &ObjectKey,
        end: &ObjectKey,
    ) -> Option<BTreeSet<ObjectKey>> {
        let (mut reachable, mut path): (HashSet<&ObjectKey>, HashSet<&ObjectKey>) =
            (HashSet::new(), HashSet::new());
        let Ok(found) = directed_path_nodes(
            (start, end),
            (
                |current: &&ObjectKey| Ok(self.edges(current, Direction::Downstream)),
                |current: &&ObjectKey| Ok(self.downstream_parents(current)),
            ),
            (&mut reachable, &mut path),
        );
        found.then(|| path.into_iter().cloned().collect())
    }

    /// Keys whose downstream list holds `key`: the inverse of the downstream edges.
    fn downstream_parents<'graph>(&'graph self, key: &ObjectKey) -> Vec<&'graph ObjectKey> {
        self.downstream
            .iter()
            .filter(|(_, children)| children.contains(key))
            .map(|(parent, _)| parent)
            .collect()
    }
}
