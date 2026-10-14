//! The reference a watermark input names in a model's upstream lineage.

use crate::planner_strategy::_helpers::lineage_walk::{LineageQueue, upstream_references};
use crate::planner_strategy::errors::LineageFailure;
use crate::planner_strategy::models::ReferenceIdentity;
use crate::planner_strategy::types::ReferenceGraph;

/// The first reference named `input`, breadth first from a model's references through model and SQL function references.
pub fn lineage_reference<G: ReferenceGraph>(
    graph: &G,
    (model, roots): (&str, Vec<G::Reference>),
    input: &str,
) -> Result<G::Reference, LineageFailure<G::Error>> {
    let mut queue: LineageQueue<G::Reference> = LineageQueue::new(roots);
    while let Some(reference) = queue.pending.pop_front() {
        let identity: ReferenceIdentity =
            graph.identity(&reference).map_err(LineageFailure::Graph)?;
        if identity.name == input {
            return Ok(reference);
        }
        if !queue.visit(&identity) {
            continue;
        }
        queue
            .pending
            .extend(upstream_references(graph, &identity).map_err(LineageFailure::Graph)?);
    }
    Err(LineageFailure::NotInLineage {
        model: model.to_owned(),
        input: input.to_owned(),
    })
}
