//! Explicit upstream source selector eligibility.

use crate::assembly::project::types::ObjectKey;
use crate::graph::errors::SelectorError;
use crate::graph::main::parse_selector::parse_selector;
use crate::graph::models::ParsedSelector;
use crate::planner_scope::constants::{NAME, SOURCE};
use std::collections::HashSet;

/// Find selected sources explicitly named by upstream source or bare-name selectors.
pub fn source_selectors(
    select: &[String],
    names: &[(String, ObjectKey)],
    selected: &[ObjectKey],
) -> Result<HashSet<ObjectKey>, SelectorError> {
    let mut keys: HashSet<ObjectKey> = HashSet::new();
    for part in select
        .iter()
        .flat_map(|raw| raw.split_whitespace())
        .flat_map(|token| token.split(','))
    {
        let ParsedSelector::Kind {
            kind,
            value,
            upstream: true,
            ..
        } = parse_selector(part)?
        else {
            continue;
        };
        if kind != NAME && kind != SOURCE {
            continue;
        }
        if let Some((_, key)) = names.iter().rev().find(|(name, _)| name == &value)
            && key.0 == SOURCE
            && selected.contains(key)
        {
            keys.insert(key.clone());
        }
    }
    Ok(keys)
}
