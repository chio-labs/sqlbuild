//! The groupings Python's `build_lookup` derives from an index and its relationship grants.

use crate::scope_index::_helpers::identities::{
    declaration_repr, declaration_text, grant_through_text, python_str_repr, resource_repr,
    resource_text,
};
use crate::scope_index::_helpers::ordering::{keyed_groups, sorted_by_key};
use crate::scope_index::_helpers::paths::normalize_path;
use crate::scope_index::_helpers::visibility::VisibilityIndex;
use crate::scope_index::models::{
    DeclarationIdentity, GrantRecord, ScopeDeferral, ScopeIndex, ScopeLookupGroups,
};

/// Every lookup grouping of `index` once `grants` are attached to it.
pub fn scope_lookup_groups(
    index: &ScopeIndex,
    grants: &[GrantRecord],
) -> Result<ScopeLookupGroups, ScopeDeferral> {
    let dependency = |usage: usize| -> &DeclarationIdentity {
        let record = index.usages[usage];
        &index.declarations[record.consumer].dependencies[record.dependency]
    };
    let consumer = |usage: usize| -> &DeclarationIdentity {
        &index.declarations[index.usages[usage].consumer].identity
    };
    let usage_indexes: Vec<usize> = (0..index.usages.len()).collect();
    let canonical_usages: Vec<usize> = sorted_by_key(&usage_indexes, |usage| {
        Ok((
            declaration_text(consumer(usage)),
            declaration_text(dependency(usage)),
        ))
    })?;
    let grant_indexes: Vec<usize> = (0..grants.len()).collect();
    let canonical_grants: Vec<usize> = sorted_by_key(&grant_indexes, |grant| {
        let record: &GrantRecord = &grants[grant];
        Ok((
            resource_text(&record.resource),
            declaration_text(&index.declarations[record.declaration].identity),
            grant_through_text(index, record),
            record.kind.as_str(),
        ))
    })?;
    let path_keys: Vec<String> = index
        .resources
        .iter()
        .map(|record| normalize_path(&record.path))
        .collect::<Result<_, _>>()?;
    Ok(ScopeLookupGroups {
        resources: keyed_groups(
            &index.canonical_resources,
            |resource| &index.resources[resource].identity,
            |identity| resource_repr(identity),
        ),
        resources_by_path: keyed_groups(
            &index.canonical_resources,
            |resource| path_keys[resource].as_str(),
            |path| python_str_repr(path),
        ),
        declarations: keyed_groups(
            &index.canonical_declarations,
            |declaration| &index.declarations[declaration].identity,
            |identity| declaration_repr(identity),
        ),
        usages_by_consumer: keyed_groups(&canonical_usages, consumer, |identity| {
            declaration_repr(identity)
        }),
        usages_by_declaration: keyed_groups(&canonical_usages, dependency, |identity| {
            declaration_repr(identity)
        }),
        grants_by_resource: keyed_groups(
            &canonical_grants,
            |grant| &grants[grant].resource,
            |identity| resource_repr(identity),
        ),
        visibility: VisibilityIndex::build(index)?.groups(),
        canonical_usages,
        canonical_grants,
    })
}
