//! Phases of relocating declarations after resource moves.

use std::collections::{HashMap, HashSet};

use crate::placement::_helpers::anchors::{
    AnchorSets, UsagesByDeclaration, anchor_sets, usages_by_declaration,
};
use crate::placement::_helpers::declaration_directory::declaration_directory;
use crate::placement::_helpers::required::required_placement;
use crate::placement::_helpers::role_layout::carried_path;
use crate::placement::models::{PlacementIndex, Relocation, RequiredPlacement};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, OwnershipRoot, OwnershipRootKind, ResourceIdentity,
    ScopeKind,
};

/// The index with every resource in `moves` at its destination.
pub(crate) fn moved_resources(
    index: &PlacementIndex,
    moves: &[(ResourceIdentity, String)],
) -> PlacementIndex {
    let mut current: PlacementIndex = index.clone();
    for record in &mut current.resources {
        if let Some((_, destination)) = moves.iter().find(|(moved, _)| *moved == record.identity) {
            record.path.clone_from(destination);
        }
    }
    current
}

/// The declarations one round moves, and whether each lacks a group its new role needs.
pub(crate) fn relocation_round(
    current: &PlacementIndex,
    misplaced: &HashSet<&DeclarationIdentity>,
) -> (
    HashMap<DeclarationIdentity, DeclarationRecord>,
    Vec<(DeclarationIdentity, bool)>,
) {
    let usages: UsagesByDeclaration<'_> = usages_by_declaration(current);
    let anchors: AnchorSets = anchor_sets(current, &usages);
    let mut relocated: HashMap<DeclarationIdentity, DeclarationRecord> = HashMap::new();
    let mut grouping: Vec<(DeclarationIdentity, bool)> = Vec::new();
    for record in &current.declarations {
        if record.scope == ScopeKind::Private || misplaced.contains(&record.identity) {
            continue;
        }
        if let Some((moved, needed)) = relocated_record(current, record, &usages, &anchors) {
            grouping.push((record.identity.clone(), needed));
            relocated.insert(record.identity.clone(), moved);
        }
    }
    (relocated, grouping)
}

/// `_relocated_record`: the record at its required placement, and whether it lacks a needed group.
fn relocated_record(
    current: &PlacementIndex,
    record: &DeclarationRecord,
    usages: &UsagesByDeclaration<'_>,
    anchors: &AnchorSets,
) -> Option<(DeclarationRecord, bool)> {
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
    let (carried, requires_group): (String, bool) = carried_path(current, record, &directory);
    let moved = DeclarationRecord {
        path: carried,
        scope,
        ownership_root,
        owning_path: if scope == ScopeKind::Global {
            None
        } else {
            path
        },
        ..record.clone()
    };
    Some((moved, requires_group))
}

/// Each declaration whose path differs from the last original record of its identity.
pub(crate) fn changed_records(
    original: &PlacementIndex,
    current: &PlacementIndex,
    requires_group: &HashSet<DeclarationIdentity>,
) -> Vec<Relocation> {
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
            requires_group: requires_group.contains(&record.identity),
        })
        .collect()
}
