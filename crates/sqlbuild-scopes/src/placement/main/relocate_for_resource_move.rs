//! The declarations whose placement follows a resource to a new path.

use std::collections::{HashMap, HashSet};

use crate::placement::_helpers::anchors::{
    AnchorSets, UsagesByDeclaration, anchor_sets, usages_by_declaration,
};
use crate::placement::_helpers::required::required_placement;
use crate::placement::main::declaration_directory::declaration_directory;
use crate::placement::main::placement_diagnostics::placement_diagnostics;
use crate::placement::models::{PlacementIndex, Relocation, RequiredPlacement};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, OwnershipRoot, OwnershipRootKind, ResourceIdentity,
    ScopeKind,
};
use sqlbuild_core::posix_path::main::posix_name::posix_name;

/// Python's `relocate_for_resource_move`: each moved declaration, or `None` when unsettled.
#[must_use]
pub fn relocate_for_resource_move(
    index: &PlacementIndex,
    resource: &ResourceIdentity,
    destination: &str,
) -> Option<Vec<Relocation>> {
    let misplaced: HashSet<&DeclarationIdentity> = placement_diagnostics(index)
        .into_iter()
        .map(|diagnostic| &index.declarations[diagnostic.declaration].identity)
        .collect();
    let mut current: PlacementIndex = index.clone();
    for record in &mut current.resources {
        if &record.identity == resource {
            record.path = destination.to_owned();
        }
    }
    for _ in 0..=index.declarations.len() {
        let usages: UsagesByDeclaration<'_> = usages_by_declaration(&current);
        let anchors: AnchorSets = anchor_sets(&current, &usages);
        let mut relocated: HashMap<DeclarationIdentity, DeclarationRecord> = HashMap::new();
        for record in &current.declarations {
            if record.scope == ScopeKind::Private || misplaced.contains(&record.identity) {
                continue;
            }
            if let Some(moved) = relocated_record(record, &usages, &anchors) {
                relocated.insert(record.identity.clone(), moved);
            }
        }
        if relocated.is_empty() {
            return Some(changed_records(index, &current));
        }
        for record in &mut current.declarations {
            if let Some(moved) = relocated.get(&record.identity) {
                *record = moved.clone();
            }
        }
    }
    None
}

/// `_relocated_record`: the record at its required placement, when that differs.
fn relocated_record(
    record: &DeclarationRecord,
    usages: &UsagesByDeclaration<'_>,
    anchors: &AnchorSets,
) -> Option<DeclarationRecord> {
    let RequiredPlacement { scope, path, .. } = required_placement(record, usages, anchors)?;
    if record.scope == scope && record.owning_path == path {
        return None;
    }
    let directory: String = declaration_directory(record.identity.kind, scope, path.as_deref());
    let roots: HashSet<&OwnershipRoot> = anchors
        .get(&record.identity)
        .into_iter()
        .flatten()
        .map(|(root, _)| root)
        .collect();
    let single_root: Option<&OwnershipRoot> = match roots.iter().next() {
        Some(root) if roots.len() == 1 && scope != ScopeKind::Global => Some(root),
        _ => None,
    };
    let ownership_root: OwnershipRoot = match single_root {
        Some(root) => (*root).clone(),
        None => OwnershipRoot {
            path: directory.clone(),
            kind: OwnershipRootKind::Global,
            resource_kind: None,
        },
    };
    Some(DeclarationRecord {
        path: format!("{directory}/{}", posix_name(&record.path)),
        scope,
        ownership_root,
        owning_path: if scope == ScopeKind::Global {
            None
        } else {
            path
        },
        ..record.clone()
    })
}

/// Each declaration whose path differs from the last original record of its identity.
fn changed_records(original: &PlacementIndex, current: &PlacementIndex) -> Vec<Relocation> {
    let paths: HashMap<&DeclarationIdentity, &str> = original
        .declarations
        .iter()
        .map(|record| (&record.identity, record.path.as_str()))
        .collect();
    current
        .declarations
        .iter()
        .enumerate()
        .filter(|(_, record)| paths.get(&record.identity) != Some(&record.path.as_str()))
        .map(|(position, record)| Relocation {
            declaration: position,
            path: record.path.clone(),
            scope: record.scope,
            ownership_root: record.ownership_root.clone(),
            owning_path: record.owning_path.clone(),
        })
        .collect()
}
