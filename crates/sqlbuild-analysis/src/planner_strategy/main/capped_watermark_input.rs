//! Watermark inputs served by capped microbatch producers.

use crate::planner_strategy::_helpers::lineage_walk::{LineageQueue, upstream_references};
use crate::planner_strategy::constants::MODEL_REFERENCE_KIND;
use crate::planner_strategy::errors::{CappedWatermarkInput, LineageFailure};
use crate::planner_strategy::main::lineage_reference::lineage_reference;
use crate::planner_strategy::models::{ProducerFacts, ReferenceIdentity};
use crate::planner_strategy::types::ReferenceGraph;

/// The first capped microbatch model upstream of a reference, following microbatch producers through their watermark inputs.
fn capped_producer<G: ReferenceGraph>(
    graph: &G,
    reference: G::Reference,
) -> Result<Option<String>, LineageFailure<G::Error>> {
    let mut queue: LineageQueue<G::Reference> = LineageQueue::new(vec![reference]);
    while let Some(current) = queue.pending.pop_front() {
        let identity: ReferenceIdentity =
            graph.identity(&current).map_err(LineageFailure::Graph)?;
        if !queue.visit(&identity) {
            continue;
        }
        if identity.kind == MODEL_REFERENCE_KIND {
            let Some(roots) = graph
                .model_references(&identity.name)
                .map_err(LineageFailure::Graph)?
            else {
                continue;
            };
            let facts: ProducerFacts = graph
                .producer_facts(&identity.name)
                .map_err(LineageFailure::Graph)?;
            if facts.microbatch && facts.capped {
                return Ok(Some(identity.name));
            }
            if facts.microbatch {
                for input in graph
                    .watermark_inputs(&identity.name)
                    .map_err(LineageFailure::Graph)?
                {
                    let next: G::Reference =
                        lineage_reference(graph, (&identity.name, roots.clone()), &input)?;
                    queue.pending.push_back(next);
                }
                continue;
            }
        }
        queue
            .pending
            .extend(upstream_references(graph, &identity).map_err(LineageFailure::Graph)?);
    }
    Ok(None)
}

/// Python's `validate_capped_watermark_inputs` for a microbatch model with these references and watermark inputs: the first input a capped producer serves.
pub fn capped_watermark_input<G: ReferenceGraph>(
    graph: &G,
    (model, roots): (&str, Vec<G::Reference>),
    inputs: Vec<String>,
) -> Result<Option<CappedWatermarkInput>, LineageFailure<G::Error>> {
    for input in inputs {
        let reference: G::Reference = lineage_reference(graph, (model, roots.clone()), &input)?;
        if let Some(producer) = capped_producer(graph, reference)? {
            return Ok(Some(CappedWatermarkInput {
                model: model.to_owned(),
                input,
                producer,
            }));
        }
    }
    Ok(None)
}
