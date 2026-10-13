//! `_resolve_model_selectors`: the resources diff `--select` names and `--exclude` does not.

use std::collections::HashSet;

use sqlbuild_core::text::main::python_isspace::python_isspace;

use crate::diff_selection::_helpers::tokens::resolve_token;
use crate::diff_selection::errors::SelectorError;
use crate::diff_selection::models::DiffGraph;

/// Every resource each whitespace-separated token of `selectors` names.
fn resolved(selectors: &[String], graph: &DiffGraph) -> Result<HashSet<usize>, SelectorError> {
    let mut keys: HashSet<usize> = HashSet::new();
    for selector in selectors {
        for token in selector
            .split(python_isspace)
            .filter(|token| !token.is_empty())
        {
            keys.extend(resolve_token(token, graph)?);
        }
    }
    Ok(keys)
}

/// The selected resources without the excluded ones, or the first selector error.
pub fn resolve_diff_selection(
    graph: &DiffGraph,
    (select, exclude): (&[String], &[String]),
) -> Result<HashSet<usize>, SelectorError> {
    let selected: HashSet<usize> = resolved(select, graph)?;
    let excluded: HashSet<usize> = resolved(exclude, graph)?;
    Ok(selected.difference(&excluded).copied().collect())
}
