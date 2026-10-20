//! New runtime usages merged into an index's declarations and usages.

use crate::compile_usages::_helpers::distinct_positions::distinct_positions;
use crate::compile_usages::_helpers::merged_dependencies::merged_dependencies;
use crate::compile_usages::models::{MergedUsages, UsageKey};
use crate::compile_usages::types::QualifiedKey;
use crate::scope_index::models::DeclarationKind;

/// Distinct `collected` usages, each declaration's merged dependencies, and the distinct prior-then-new usages.
#[must_use]
pub fn merged_usages(
    declarations: &[(QualifiedKey, Option<Vec<QualifiedKey>>)],
    prior: &[UsageKey],
    collected: &[UsageKey],
) -> MergedUsages {
    let distinct: Vec<usize> = distinct_positions(collected);
    let mut consumed: Vec<(Option<QualifiedKey>, QualifiedKey)> =
        Vec::with_capacity(distinct.len());
    for position in &distinct {
        let UsageKey {
            consumer,
            declaration,
            ..
        } = &collected[*position];
        let by_declaration: Option<QualifiedKey> = DeclarationKind::parse(&consumer.0)
            .is_some()
            .then(|| consumer.clone());
        consumed.push((by_declaration, declaration.clone()));
    }
    let merged = merged_dependencies(declarations, &consumed);
    let mut combined: Vec<&UsageKey> = prior.iter().collect();
    combined.extend(distinct.iter().map(|position| &collected[*position]));
    let combined: Vec<usize> = distinct_positions(&combined);
    MergedUsages {
        distinct,
        merged,
        combined,
    }
}
