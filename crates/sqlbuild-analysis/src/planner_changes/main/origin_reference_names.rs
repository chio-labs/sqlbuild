//! Recognize a query whose only change is `__ref` names rewritten for renamed models.

use std::collections::BTreeSet;

use crate::planner_changes::_helpers::rename_mappings::{lineage, product, substitute};
use crate::planner_changes::constants::MAX_CANDIDATE_MAPPINGS;
use crate::planner_changes::models::{NameSpan, RenameCandidate};
use crate::planner_changes::types::RenameMatching;

/// The first rename mapping (in name order, at most 64 tried) under which the query hashes to `recorded_hash`.
pub fn origin_reference_names<E>(
    (query_sql, recorded_hash): (&str, &str),
    renames: &[RenameCandidate],
    (find_spans, query_hash): RenameMatching<'_, E>,
) -> Result<Option<Vec<(String, String)>>, E> {
    let mut origins: Vec<(String, Vec<String>)> = Vec::new();
    for rename in renames.iter().filter(|rename| rename.applies) {
        match origins
            .iter_mut()
            .find(|(name, _)| *name == rename.new_name)
        {
            Some((_, list)) => list.push(rename.origin_name.clone()),
            None => origins.push((rename.new_name.clone(), vec![rename.origin_name.clone()])),
        }
    }
    if origins.is_empty() {
        return Ok(None);
    }
    let keys: BTreeSet<String> = origins.iter().map(|(name, _)| name.clone()).collect();
    let spans: Vec<NameSpan> = find_spans(&keys)?;
    let names: Vec<String> = spans
        .iter()
        .map(|span| span.name.clone())
        .collect::<BTreeSet<String>>()
        .into_iter()
        .collect();
    let choices: Vec<Vec<String>> = names.iter().map(|name| lineage(name, &origins)).collect();
    let characters: Vec<char> = query_sql.chars().collect();
    for combination in product(&choices).into_iter().take(MAX_CANDIDATE_MAPPINGS) {
        let mapping: Vec<(String, String)> = names
            .iter()
            .zip(combination)
            .filter(|(name, origin)| *name != origin)
            .map(|(name, origin)| (name.clone(), origin))
            .collect();
        if mapping.is_empty() {
            continue;
        }
        if query_hash(&substitute(&characters, &spans, &mapping))? == recorded_hash {
            return Ok(Some(mapping));
        }
    }
    Ok(None)
}
