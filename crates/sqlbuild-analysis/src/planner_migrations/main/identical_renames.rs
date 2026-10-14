//! Select unique expression matches, then prove the complete query change.

use std::collections::BTreeSet;

use crate::planner_migrations::_helpers::proofs::removed_and_added::removed_and_added;
use crate::planner_migrations::models::Projection;
use crate::planner_migrations::types::RenameProof;

/// Unique old/new names in current projection order, only when the complete rename proof succeeds.
pub fn identical_renames<E>(
    shapes: (&[Projection], &[Projection]),
    excluded: &BTreeSet<String>,
    explains_change: &mut RenameProof<'_, E>,
) -> Result<Vec<(String, String)>, E> {
    let (removed, added) = removed_and_added(shapes, excluded);
    let mut pairs: Vec<(String, String)> = Vec::new();
    for column in &added {
        let mut matches = removed
            .iter()
            .filter(|origin| origin.expression == column.expression);
        let Some(origin) = matches.next() else {
            continue;
        };
        if matches.next().is_some() {
            continue;
        }
        if added
            .iter()
            .filter(|other| other.expression == origin.expression)
            .count()
            == 1
        {
            pairs.push((origin.name.clone(), column.name.clone()));
        }
    }
    if pairs.is_empty() || !explains_change(&pairs)? {
        return Ok(Vec::new());
    }
    Ok(pairs)
}
