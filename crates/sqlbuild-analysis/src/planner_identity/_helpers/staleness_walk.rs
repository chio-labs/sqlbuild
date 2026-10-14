//! The upstream staleness walk of one selected model.

use std::collections::{BTreeSet, HashMap, HashSet};

use crate::planner_identity::constants::{MODEL_RESOURCE, SEED_RESOURCE, SOURCE_RESOURCE};
use crate::planner_identity::models::{GraphKey, StalenessGraph};

/// The upstream walk of one selected model.
pub(crate) struct StalenessWalk<'a> {
    pub(crate) graph: &'a StalenessGraph,
    pub(crate) model_key: &'a GraphKey,
    pub(crate) names: BTreeSet<String>,
    pub(crate) visiting: HashSet<GraphKey>,
    pub(crate) stale: HashMap<GraphKey, bool>,
}

impl StalenessWalk<'_> {
    pub(crate) fn visit(&mut self, key: &GraphKey) -> bool {
        if let Some(cached) = self.stale.get(key) {
            return *cached;
        }
        if self.visiting.contains(key) {
            return false;
        }
        self.visiting.insert(key.clone());
        let graph: &StalenessGraph = self.graph;
        let is_stale: bool = match key.kind.as_str() {
            MODEL_RESOURCE => {
                let in_run_set: bool = graph.run.models.contains(&key.name);
                if graph.changed.models.contains(&key.name) && !in_run_set {
                    self.names.insert(key.name.clone());
                    true
                } else {
                    let mut ancestor_stale: bool = false;
                    for parent_key in graph.upstream_deps.get(key).into_iter().flatten() {
                        let parent_stale: bool = self.visit(parent_key);
                        ancestor_stale = parent_stale || ancestor_stale;
                        if run_parent_changed(graph, parent_key) {
                            ancestor_stale = true;
                        }
                    }
                    if ancestor_stale && !in_run_set && key != self.model_key {
                        self.names.insert(key.name.clone());
                    }
                    ancestor_stale
                }
            }
            SEED_RESOURCE => self.leaf(key, (&graph.changed.seeds, &graph.run.seeds)),
            SOURCE_RESOURCE => self.leaf(key, (&graph.changed.sources, &graph.run.sources)),
            _ => false,
        };
        self.visiting.remove(key);
        self.stale.insert(key.clone(), is_stale);
        is_stale
    }

    fn leaf(
        &mut self,
        key: &GraphKey,
        (changed, run): (&HashSet<String>, &HashSet<String>),
    ) -> bool {
        let is_changed: bool = changed.contains(&key.name);
        if is_changed && !run.contains(&key.name) {
            self.names.insert(key.name.clone());
        }
        is_changed
    }
}

fn run_parent_changed(graph: &StalenessGraph, parent_key: &GraphKey) -> bool {
    let (run, changed): (&HashSet<String>, &HashSet<String>) = match parent_key.kind.as_str() {
        MODEL_RESOURCE => (&graph.run.models, &graph.changed.models),
        SEED_RESOURCE => (&graph.run.seeds, &graph.changed.seeds),
        SOURCE_RESOURCE => (&graph.run.sources, &graph.changed.sources),
        _ => return false,
    };
    run.contains(&parent_key.name) && changed.contains(&parent_key.name)
}
