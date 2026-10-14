//! Breadth-first walks over SQL reference lineage.

use std::collections::{HashSet, VecDeque};

use crate::planner_strategy::constants::{FUNCTION_REFERENCE_KINDS, MODEL_REFERENCE_KIND};
use crate::planner_strategy::models::ReferenceIdentity;
use crate::planner_strategy::types::ReferenceGraph;

/// The references a model or function reference reads, when the project has its target.
pub(crate) fn upstream_references<G: ReferenceGraph>(
    graph: &G,
    identity: &ReferenceIdentity,
) -> Result<Vec<G::Reference>, G::Error> {
    let references: Option<Vec<G::Reference>> = if identity.kind == MODEL_REFERENCE_KIND {
        graph.model_references(&identity.name)?
    } else if FUNCTION_REFERENCE_KINDS.contains(&identity.kind.as_str()) {
        graph.function_references(&identity.name)?
    } else {
        None
    };
    Ok(references.unwrap_or_default())
}

/// A first-in, first-out queue of references that skips identities it has expanded.
pub(crate) struct LineageQueue<R> {
    pub(crate) pending: VecDeque<R>,
    pub(crate) visited: HashSet<ReferenceIdentity>,
}

impl<R> LineageQueue<R> {
    pub(crate) fn new(roots: Vec<R>) -> Self {
        Self {
            pending: roots.into(),
            visited: HashSet::new(),
        }
    }

    /// Whether an identity is newly visited.
    pub(crate) fn visit(&mut self, identity: &ReferenceIdentity) -> bool {
        self.visited.insert(identity.clone())
    }
}
