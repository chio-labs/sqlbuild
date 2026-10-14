//! Selected models stale through changed upstreams outside the run set.

use std::collections::{BTreeSet, HashMap, HashSet};

use crate::planner_identity::_helpers::staleness_walk::StalenessWalk;

use crate::planner_identity::constants::MODEL_RESOURCE;
use crate::planner_identity::models::{GraphKey, StaleWarning, StalenessGraph};

/// One warning per selected model, by name, whose upstream closure reaches a changed node that does not run.
pub fn classify_selection_staleness(graph: &StalenessGraph) -> Vec<StaleWarning> {
    let selected: BTreeSet<&String> = graph.selected_model_names.iter().collect();
    let mut warnings: Vec<StaleWarning> = Vec::new();
    for model_name in selected {
        let model_key = GraphKey {
            kind: MODEL_RESOURCE.to_owned(),
            name: model_name.clone(),
        };
        let mut walk = StalenessWalk {
            graph,
            model_key: &model_key,
            names: BTreeSet::new(),
            visiting: HashSet::new(),
            stale: HashMap::new(),
        };
        for upstream_key in graph.upstream_deps.get(&model_key).into_iter().flatten() {
            let _ = walk.visit(upstream_key);
        }
        if !walk.names.is_empty() {
            warnings.push(StaleWarning {
                model_name: model_name.clone(),
                trigger_names: walk.names.into_iter().collect(),
            });
        }
    }
    warnings
}
