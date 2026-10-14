//! Whether a selector term anchors SQLBuild work on dbt nodes.

use crate::dbt_graph::constants::PATH_SELECTOR_SEPARATOR;
use crate::dbt_graph::models::DbtSelectorExpansion;
use crate::dbt_graph::types::DbtSelectorResolver;

/// A trailing-plus term that is neither a path selector nor a SQLBuild model selector.
pub fn dbt_anchor_term_check<E>(
    resolver: &impl DbtSelectorResolver<Error = E>,
    term: &str,
) -> Result<bool, E> {
    let parsed: DbtSelectorExpansion = resolver.split(term)?;
    if !parsed.downstream || parsed.core.contains(PATH_SELECTOR_SEPARATOR) {
        return Ok(false);
    }
    Ok(resolver.model_names(&parsed.core)?.0.is_empty())
}
