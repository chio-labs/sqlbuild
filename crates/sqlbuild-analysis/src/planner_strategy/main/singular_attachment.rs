//! Where a singular audit attaches, from its references and the model graph.

use crate::planner_strategy::models::AuditAttachmentKind;
use crate::planner_strategy::types::Reaches;

/// Whether every other referenced model reaches `candidate`.
fn reached_by_all<E>(
    candidate: &str,
    models: &[String],
    reaches: &Reaches<'_, E>,
) -> Result<bool, E> {
    for other in models {
        if other != candidate && !reaches(other, candidate)? {
            return Ok(false);
        }
    }
    Ok(true)
}

/// The single model every other referenced model reaches, if there is one.
fn latest_owner<E>(models: &[String], reaches: &Reaches<'_, E>) -> Result<Option<String>, E> {
    let mut candidates: Vec<&String> = Vec::new();
    for candidate in models {
        if reached_by_all(candidate, models, reaches)? {
            candidates.push(candidate);
        }
    }
    if candidates.len() == 1 {
        return Ok(Some(candidates[0].clone()));
    }
    if candidates.is_empty() {
        return Ok(None);
    }
    candidates.sort();
    let mut deepest: &String = candidates[0];
    for other in &candidates[1..] {
        if reaches(deepest, other)? {
            deepest = other;
        }
    }
    Ok(reached_by_all(deepest, models, reaches)?.then(|| deepest.clone()))
}

/// Python's `_infer_singular_attachment` over the audit's model and source reference names.
pub fn singular_attachment<E>(
    model_references: &[String],
    source_references: &[String],
    reaches: &Reaches<'_, E>,
) -> Result<(AuditAttachmentKind, Option<String>), E> {
    if model_references.is_empty() {
        return Ok(match source_references.iter().min() {
            Some(source) => (AuditAttachmentKind::Source, Some(source.clone())),
            None => (AuditAttachmentKind::End, None),
        });
    }
    if let [model] = model_references {
        return Ok((AuditAttachmentKind::Model, Some(model.clone())));
    }
    Ok(match latest_owner(model_references, reaches)? {
        Some(owner) => (AuditAttachmentKind::Model, Some(owner)),
        None => (AuditAttachmentKind::End, None),
    })
}
