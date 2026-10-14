//! Prove that output renames explain the entire query change.

use crate::planner_migrations::_helpers::proofs::binding_proof::{binding_proven, substitute};
use crate::planner_migrations::_helpers::proofs::encoding::encode;
use crate::planner_migrations::models::QueryShape;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

/// Whether names and alias bindings are the only change, preserving callback failures.
pub fn renames_explain_change<E: From<String>>(
    shapes: (&QueryShape, &QueryShape),
    renames: &[(String, String)],
    mut input_columns: impl FnMut(&str, &str) -> Result<Option<BTreeSet<String>>, E>,
) -> Result<bool, E> {
    let (previous, current) = shapes;
    if renames.is_empty() || previous.body != current.body {
        return Ok(false);
    }
    let mut lowered: Vec<(String, String)> = Vec::new();
    for (old, new) in renames {
        let old = old.to_lowercase();
        let new = new.to_lowercase();
        if let Some(pair) = lowered.iter_mut().find(|pair| pair.0 == old) {
            pair.1 = new;
        } else {
            lowered.push((old, new));
        }
    }
    let key = |name: &str| {
        let key = name.to_lowercase();
        lowered
            .iter()
            .find(|pair| pair.0 == key)
            .map_or(key.clone(), |pair| pair.1.clone())
    };
    let renamed: BTreeMap<String, &str> = previous
        .projections
        .iter()
        .map(|item| (key(&item.name), item.expression.as_str()))
        .collect();
    let desired: BTreeMap<String, &str> = current
        .projections
        .iter()
        .map(|item| (item.name.to_lowercase(), item.expression.as_str()))
        .collect();
    if renamed.len() != previous.projections.len() || renamed != desired {
        return Ok(false);
    }
    let reordered = previous
        .projections
        .iter()
        .map(|item| key(&item.name))
        .ne(current
            .projections
            .iter()
            .map(|item| item.name.to_lowercase()));
    if reordered && (previous.positional || current.positional) {
        return Ok(false);
    }
    for (origin, destination) in &lowered {
        if !binding_proven(shapes, (origin, destination), &mut input_columns)? {
            return Ok(false);
        }
    }
    let mut restored: Value =
        serde_json::from_str(&current.alias_clauses).map_err(|error| E::from(error.to_string()))?;
    substitute(
        &mut restored,
        &lowered
            .into_iter()
            .map(|(old, new)| (new, old))
            .collect::<Vec<_>>(),
    );
    Ok(encode(&restored).map_err(E::from)? == previous.alias_clauses)
}
