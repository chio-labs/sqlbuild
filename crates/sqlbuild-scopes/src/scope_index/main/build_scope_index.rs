//! Project the builder's walked resources and declarations into the static scope index.

use crate::scope_index::_helpers::diagnostics::scope_diagnostics;
use crate::scope_index::_helpers::ordering::{
    canonical_declaration_key, canonical_resource_key, declaration_key, resource_key, sorted_by_key,
};
use crate::scope_index::_helpers::records::{
    declaration_record, dependency_usages, resource_record,
};
use crate::scope_index::_helpers::visibility::VisibilityIndex;
use crate::scope_index::models::{DeclarationKind, ScopeKind};
use crate::scope_index::models::{
    DeclarationRecord, ResourceRecord, ScopeDeferral, ScopeIndex, ScopeInputs, UsageRecord,
};

/// Python's `build_index` for loaded macros, plus the lookup's canonical record orders.
pub fn build_scope_index(inputs: ScopeInputs) -> Result<ScopeIndex, ScopeDeferral> {
    let resources: Vec<ResourceRecord> = inputs
        .resources
        .into_iter()
        .map(resource_record)
        .collect::<Result<_, _>>()?;
    let declarations: Vec<DeclarationRecord> = inputs
        .declarations
        .into_iter()
        .map(declaration_record)
        .collect::<Result<_, _>>()?;
    let resource_indexes: Vec<usize> = (0..resources.len()).collect();
    let declaration_indexes: Vec<usize> = (0..declarations.len()).collect();
    let resource_order: Vec<usize> = sorted_by_key(&resource_indexes, |index| {
        Ok(resource_key(&resources[index]))
    })?;
    let declaration_order: Vec<usize> = sorted_by_key(&declaration_indexes, |index| {
        Ok(declaration_key(&declarations[index]))
    })?;
    let canonical_resources: Vec<usize> = sorted_by_key(&resource_order, |index| {
        canonical_resource_key(&resources[index])
    })?;
    let canonical_declarations: Vec<usize> = sorted_by_key(&declaration_order, |index| {
        canonical_declaration_key(&declarations[index])
    })?;
    let usages: Vec<UsageRecord> = dependency_usages(&declarations);
    let diagnostics = scope_diagnostics(&resources, &declarations);
    let has_scoped_relationship_declarations: bool = declarations.iter().any(|declaration| {
        declaration.scope != ScopeKind::Global
            && matches!(
                declaration.identity.kind,
                DeclarationKind::Enum | DeclarationKind::Constant | DeclarationKind::Macro
            )
    });
    let index: ScopeIndex = ScopeIndex {
        resources,
        declarations,
        resource_order,
        declaration_order,
        canonical_resources,
        canonical_declarations,
        usages,
        diagnostics,
        has_scoped_relationship_declarations,
    };
    VisibilityIndex::build(&index)?;
    Ok(index)
}
