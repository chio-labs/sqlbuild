//! Python's `build_lookup` over a full scope index's records.

use crate::scope_index::_helpers::identities::{
    declaration_repr, declaration_text, qualified_repr, qualified_text, resource_repr,
    resource_text,
};
use crate::scope_index::_helpers::ordering::keyed_groups;
use crate::scope_index::_helpers::paths::checked_path;
use crate::scope_index::_helpers::visibility::{VisibilityIndex, checked_owner};
use crate::scope_index::models::{
    RejectedPath, ReportGroups, ReportLookup, ReportRecords, ScopeIndex, ScopeKind,
};
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

/// Stable `sorted(range(count), key=key)`.
fn sorted_positions<K: Ord>(count: usize, key: impl Fn(usize) -> K) -> Vec<usize> {
    let mut positions: Vec<usize> = (0..count).collect();
    positions.sort_by_cached_key(|position| key(*position));
    positions
}

/// Every canonical order, lookup mapping and visibility group, or the path Python rejects first.
pub fn report_lookup(records: &ReportRecords) -> Result<ReportLookup, RejectedPath> {
    let resource_paths: Vec<String> = records
        .resources
        .iter()
        .map(|record| checked_path(&record.path))
        .collect::<Result<_, _>>()?;
    let declaration_paths: Vec<String> = records
        .declarations
        .iter()
        .map(|record| checked_path(&record.path))
        .collect::<Result<_, _>>()?;
    let resources: Vec<usize> = sorted_positions(records.resources.len(), |resource| {
        (
            resource_text(&records.resources[resource].identity),
            resource_paths[resource].clone(),
        )
    });
    let declarations: Vec<usize> = sorted_positions(records.declarations.len(), |declaration| {
        let record = &records.declarations[declaration];
        (
            declaration_text(&record.identity),
            declaration_paths[declaration].clone(),
            record.line.to_string(),
            record.column.to_string(),
        )
    });
    for declaration in &declarations {
        let record = &records.declarations[*declaration];
        if matches!(record.scope, ScopeKind::Local | ScopeKind::Inherited) {
            checked_owner(record)?;
        }
    }
    let usages: Vec<usize> = sorted_positions(records.usages.len(), |usage| {
        let record = &records.usages[usage];
        (
            qualified_text(&record.consumer),
            declaration_text(&record.declaration),
            record.kind.clone(),
            record
                .through
                .as_ref()
                .map(qualified_text)
                .unwrap_or_default(),
        )
    });
    let grants: Vec<usize> = sorted_positions(records.grants.len(), |grant| {
        let record = &records.grants[grant];
        (
            resource_text(&record.resource),
            declaration_text(&record.declaration),
            qualified_text(&record.through),
            record.kind.as_str(),
        )
    });
    let roots: Vec<usize> = sorted_positions(records.roots.len(), |root| {
        let record = &records.roots[root];
        (
            record.path.clone(),
            record
                .resource_kind
                .map(super::super::models::ResourceKind::as_str)
                .unwrap_or_default(),
        )
    });
    let diagnostics: Vec<usize> = sorted_positions(records.diagnostics.len(), |diagnostic| {
        let record = &records.diagnostics[diagnostic];
        (
            record.path.clone().unwrap_or_default(),
            record.line.unwrap_or(0),
            record.column.unwrap_or(0),
            record.code.clone(),
        )
    });
    let groups: ReportGroups = ReportGroups {
        resources: keyed_groups(
            &resources,
            |resource| &records.resources[resource].identity,
            |identity| resource_repr(identity),
        ),
        resources_by_path: keyed_groups(
            &resources,
            |resource| resource_paths[resource].as_str(),
            |path| python_str_repr(path),
        ),
        declarations: keyed_groups(
            &declarations,
            |declaration| &records.declarations[declaration].identity,
            |identity| declaration_repr(identity),
        ),
        usages_by_consumer: keyed_groups(
            &usages,
            |usage| &records.usages[usage].consumer,
            |identity| qualified_repr(identity),
        ),
        usages_by_declaration: keyed_groups(
            &usages,
            |usage| &records.usages[usage].declaration,
            |identity| declaration_repr(identity),
        ),
        grants_by_resource: keyed_groups(
            &grants,
            |grant| &records.grants[grant].resource,
            |identity| resource_repr(identity),
        ),
    };
    let index: ScopeIndex = ScopeIndex {
        declarations: records.declarations.clone(),
        canonical_declarations: declarations.clone(),
        ..ScopeIndex::default()
    };
    let visibility = VisibilityIndex::build(&index)
        .map_err(|_| RejectedPath {
            failure: crate::scope_index::models::ScopePathFailure::NotProjectRelative,
            path: String::new(),
        })?
        .groups();
    Ok(ReportLookup {
        roots,
        resources,
        declarations,
        usages,
        grants,
        diagnostics,
        groups,
        visibility,
        resource_paths,
    })
}
