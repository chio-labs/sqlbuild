//! Builder records from walked inputs, and the macro dependency usages between them.

use crate::scope_index::_helpers::paths::normalize_path;
use crate::scope_index::_helpers::roots::{declaration_root, resource_root};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationInput, DeclarationRecord, ResourceInput, ResourceRecord,
    ScopeDeferral, UsageRecord,
};
use std::collections::HashSet;

/// Python's `_resource_record` and the seed and Python function records.
pub(crate) fn resource_record(input: ResourceInput) -> Result<ResourceRecord, ScopeDeferral> {
    Ok(ResourceRecord {
        ownership_root: resource_root(input.identity.kind, input.root)?,
        path: normalize_path(&input.path)?,
        identity: input.identity,
    })
}

/// Python's declaration records, before value metadata the facade attaches.
pub(crate) fn declaration_record(
    input: DeclarationInput,
) -> Result<DeclarationRecord, ScopeDeferral> {
    Ok(DeclarationRecord {
        ownership_root: declaration_root(input.ownership_root.as_deref(), &input.root_fallback)?,
        path: normalize_path(&input.path)?,
        owning_path: input
            .owning_path
            .as_deref()
            .map(normalize_path)
            .transpose()?,
        identity: input.identity,
        line: input.line,
        column: 1,
        scope: input.scope,
        dependencies: input.dependencies,
    })
}

/// Python's `_macro_dependency_usages`: every dependency edge once, in declaration input order.
pub(crate) fn dependency_usages(declarations: &[DeclarationRecord]) -> Vec<UsageRecord> {
    let mut seen: HashSet<(&DeclarationIdentity, &DeclarationIdentity)> = HashSet::new();
    let mut usages: Vec<UsageRecord> = Vec::new();
    for (consumer, record) in declarations.iter().enumerate() {
        for (dependency, identity) in record.dependencies.iter().enumerate() {
            if seen.insert((&record.identity, identity)) {
                usages.push(UsageRecord {
                    consumer,
                    dependency,
                });
            }
        }
    }
    usages
}
