//! Expected-model and tested-macro grants, as Python's `build_scope_relationship_grants` makes them.

use crate::scope_index::_helpers::grants::{GrantResolver, unique_grants};
use crate::scope_index::models::{GrantRecord, RelationshipFact, ScopeDeferral, ScopeIndex};

/// The relationship grants of every fact, in Python's order and deduplicated like `dict.fromkeys`.
pub fn relationship_grants(
    index: &ScopeIndex,
    facts: &[RelationshipFact],
) -> Result<Vec<GrantRecord>, ScopeDeferral> {
    let resolver: GrantResolver<'_> = GrantResolver::new(index)?;
    let mut grants: Vec<GrantRecord> = Vec::new();
    for fact in facts {
        grants.extend(resolver.expected_model_grants(fact)?);
        grants.extend(resolver.tested_macro_grants(fact)?);
    }
    Ok(unique_grants(index, grants))
}
