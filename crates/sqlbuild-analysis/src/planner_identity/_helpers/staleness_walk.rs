//! The upstream staleness walk of one selected model, with an explicit stack.

use std::collections::{BTreeSet, HashMap, HashSet};

use crate::planner_identity::constants::{MODEL_RESOURCE, SEED_RESOURCE, SOURCE_RESOURCE};
use crate::planner_identity::models::{GraphKey, StalenessGraph};

/// A model whose parents are being visited.
struct Frame<'a> {
    key: &'a GraphKey,
    parents: &'a [GraphKey],
    next_parent: usize,
    in_run_set: bool,
    ancestor_stale: bool,
}

/// What entering a node yields: its staleness already, or a frame to walk.
enum Entered<'a> {
    Resolved(bool),
    Pending(Frame<'a>),
}

/// The upstream walk of one selected model.
pub(crate) struct StalenessWalk<'a> {
    pub(crate) graph: &'a StalenessGraph,
    pub(crate) model_key: &'a GraphKey,
    pub(crate) names: BTreeSet<String>,
    pub(crate) visiting: HashSet<GraphKey>,
    pub(crate) stale: HashMap<GraphKey, bool>,
}

impl<'a> StalenessWalk<'a> {
    pub(crate) fn visit(&mut self, root: &'a GraphKey) -> bool {
        let mut stack: Vec<Frame<'a>> = match self.enter(root) {
            Entered::Resolved(is_stale) => return is_stale,
            Entered::Pending(frame) => vec![frame],
        };
        let graph: &'a StalenessGraph = self.graph;
        while let Some(frame) = stack.last_mut() {
            if let Some(parent_key) = frame.parents.get(frame.next_parent) {
                frame.next_parent += 1;
                match self.enter(parent_key) {
                    Entered::Resolved(parent_stale) => {
                        frame.ancestor_stale =
                            absorbed(frame.ancestor_stale, (graph, parent_key), parent_stale);
                    }
                    Entered::Pending(parent_frame) => stack.push(parent_frame),
                }
                continue;
            }
            let Some(finished) = stack.pop() else {
                break;
            };
            let is_stale: bool = self.finish(&finished);
            match stack.last_mut() {
                Some(child) => {
                    child.ancestor_stale =
                        absorbed(child.ancestor_stale, (graph, finished.key), is_stale);
                }
                None => return is_stale,
            }
        }
        false
    }

    fn enter(&mut self, key: &'a GraphKey) -> Entered<'a> {
        if let Some(cached) = self.stale.get(key) {
            return Entered::Resolved(*cached);
        }
        if self.visiting.contains(key) {
            return Entered::Resolved(false);
        }
        let graph: &'a StalenessGraph = self.graph;
        let is_stale: bool = match key.kind.as_str() {
            MODEL_RESOURCE => {
                let in_run_set: bool = graph.run.models.contains(&key.name);
                if graph.changed.models.contains(&key.name) && !in_run_set {
                    self.names.insert(key.name.clone());
                    true
                } else {
                    self.visiting.insert(key.clone());
                    return Entered::Pending(Frame {
                        key,
                        parents: graph.upstream_deps.get(key).map_or(&[], Vec::as_slice),
                        next_parent: 0,
                        in_run_set,
                        ancestor_stale: false,
                    });
                }
            }
            SEED_RESOURCE => self.leaf(key, (&graph.changed.seeds, &graph.run.seeds)),
            SOURCE_RESOURCE => self.leaf(key, (&graph.changed.sources, &graph.run.sources)),
            _ => false,
        };
        self.stale.insert(key.clone(), is_stale);
        Entered::Resolved(is_stale)
    }

    fn finish(&mut self, frame: &Frame<'a>) -> bool {
        if frame.ancestor_stale && !frame.in_run_set && frame.key != self.model_key {
            self.names.insert(frame.key.name.clone());
        }
        self.visiting.remove(frame.key);
        self.stale.insert(frame.key.clone(), frame.ancestor_stale);
        frame.ancestor_stale
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

fn absorbed(
    ancestor_stale: bool,
    (graph, parent_key): (&StalenessGraph, &GraphKey),
    parent_stale: bool,
) -> bool {
    parent_stale || ancestor_stale || run_parent_changed(graph, parent_key)
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
