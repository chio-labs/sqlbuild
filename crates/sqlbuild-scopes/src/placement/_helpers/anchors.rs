//! The resource folders each declaration's consumers anchor it to, through consumer chains.

use std::collections::{HashMap, HashSet, VecDeque};

use crate::placement::_helpers::roles::is_named_kind;
use crate::placement::constants::PROJECT_ROOT_PATH;
use crate::placement::models::{PlacementIndex, PlacementUsage};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, OwnershipRoot, OwnershipRootKind, QualifiedIdentity,
    ResourceIdentity, ResourceRecord,
};
use sqlbuild_core::posix_path::main::posix_parent::posix_parent;

/// An ownership root and the folder below it a consumer sits in.
pub(crate) type Anchor = (OwnershipRoot, String);
/// Each declaration's usages, in index order.
pub(crate) type UsagesByDeclaration<'a> = HashMap<&'a DeclarationIdentity, Vec<&'a PlacementUsage>>;
/// Each declaration's anchors.
pub(crate) type AnchorSets = HashMap<DeclarationIdentity, HashSet<Anchor>>;

/// `_usages_by_declaration`.
pub(crate) fn usages_by_declaration(index: &PlacementIndex) -> UsagesByDeclaration<'_> {
    let mut grouped: UsagesByDeclaration<'_> = HashMap::new();
    for usage in &index.usages {
        grouped.entry(&usage.declaration).or_default().push(usage);
    }
    grouped
}

/// `_anchor_sets`: direct anchors, then anchors propagated to declarations their dependents use.
pub(crate) fn anchor_sets(index: &PlacementIndex, usages: &UsagesByDeclaration<'_>) -> AnchorSets {
    let resources: HashMap<&ResourceIdentity, &ResourceRecord> = index
        .resources
        .iter()
        .map(|record| (&record.identity, record))
        .collect();
    let declarations: HashMap<&DeclarationIdentity, &DeclarationRecord> = index
        .declarations
        .iter()
        .map(|record| (&record.identity, record))
        .collect();
    let mut anchors: AnchorSets = HashMap::new();
    let mut dependents: HashMap<DeclarationIdentity, HashSet<DeclarationIdentity>> = HashMap::new();
    for (identity, declaration_usages) in usages {
        let mut direct: HashSet<Anchor> = HashSet::new();
        for usage in declaration_usages {
            match direct_anchor(usage, &resources, &declarations) {
                DirectAnchor::Anchor(anchor) => {
                    direct.insert(anchor);
                }
                DirectAnchor::Dependent(consumer) => {
                    dependents
                        .entry(consumer.clone())
                        .or_default()
                        .insert((*identity).clone());
                }
                DirectAnchor::None => {}
            }
        }
        anchors
            .entry((*identity).clone())
            .or_default()
            .extend(direct);
    }
    let mut pending: VecDeque<DeclarationIdentity> = anchors.keys().cloned().collect();
    while let Some(source) = pending.pop_front() {
        let source_anchors: HashSet<Anchor> = anchors.get(&source).cloned().unwrap_or_default();
        let Some(targets) = dependents.get(&source) else {
            continue;
        };
        for target in targets {
            let target_anchors: &mut HashSet<Anchor> = anchors.entry(target.clone()).or_default();
            if source_anchors.is_subset(target_anchors) {
                continue;
            }
            target_anchors.extend(source_anchors.iter().cloned());
            pending.push_back(target.clone());
        }
    }
    anchors
}

/// What one usage contributes: an anchor, a declaration consumer to inherit from, or nothing.
enum DirectAnchor<'a> {
    Anchor(Anchor),
    Dependent(&'a DeclarationIdentity),
    None,
}

fn direct_anchor<'a>(
    usage: &'a PlacementUsage,
    resources: &HashMap<&ResourceIdentity, &ResourceRecord>,
    declarations: &HashMap<&DeclarationIdentity, &DeclarationRecord>,
) -> DirectAnchor<'a> {
    if let Some(QualifiedIdentity::Declaration(through)) = &usage.through {
        return match declarations.get(through) {
            Some(record) => match &record.owning_path {
                Some(path) => DirectAnchor::Anchor((record.ownership_root.clone(), path.clone())),
                None => DirectAnchor::None,
            },
            None => DirectAnchor::None,
        };
    }
    if let (None, QualifiedIdentity::Declaration(consumer)) = (&usage.through, &usage.consumer)
        && is_named_kind(consumer.kind)
    {
        return match declarations.get(consumer) {
            Some(record) => DirectAnchor::Anchor(location_anchor(record)),
            None => DirectAnchor::None,
        };
    }
    let resource: Option<&ResourceIdentity> = match (&usage.through, &usage.consumer) {
        (Some(QualifiedIdentity::Resource(through)), _) => Some(through),
        (None, QualifiedIdentity::Resource(consumer)) => Some(consumer),
        _ => None,
    };
    match (resource, &usage.consumer) {
        (Some(identity), _) => match resources.get(identity) {
            Some(record) => {
                DirectAnchor::Anchor((record.ownership_root.clone(), posix_parent(&record.path)))
            }
            None => DirectAnchor::None,
        },
        (None, QualifiedIdentity::Declaration(consumer)) => DirectAnchor::Dependent(consumer),
        (None, QualifiedIdentity::Resource(_)) => DirectAnchor::None,
    }
}

/// `_declaration_location_anchor`: where an audit, schema or hook using a declaration lives.
fn location_anchor(record: &DeclarationRecord) -> Anchor {
    match &record.owning_path {
        None => (
            OwnershipRoot {
                path: PROJECT_ROOT_PATH.to_owned(),
                kind: OwnershipRootKind::Global,
                resource_kind: None,
            },
            PROJECT_ROOT_PATH.to_owned(),
        ),
        Some(path) => (record.ownership_root.clone(), path.clone()),
    }
}
