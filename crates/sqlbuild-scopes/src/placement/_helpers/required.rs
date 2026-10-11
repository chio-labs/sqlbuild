//! `_required_placement_for_record`: the scope and folder a declaration's consumers require.

use std::collections::{BTreeSet, HashSet};

use crate::placement::_helpers::anchors::{Anchor, AnchorSets, UsagesByDeclaration};
use crate::placement::_helpers::posix_paths::common_prefix;
use crate::placement::_helpers::roles::is_named_kind;
use crate::placement::models::{PlacementUsage, RequiredPlacement};
use crate::scope_index::main::format_identity::format_identity;
use crate::scope_index::models::{
    DeclarationKind, DeclarationRecord, OwnershipRoot, OwnershipRootKind, QualifiedIdentity,
    ScopeKind,
};

/// Whether a private declaration's owner uses it directly.
pub(crate) fn owner_uses_directly(record: &DeclarationRecord, usage: &PlacementUsage) -> bool {
    let owner: Option<QualifiedIdentity> = record
        .identity
        .owner
        .clone()
        .map(QualifiedIdentity::Resource);
    usage.through.is_none() && owner.as_ref() == Some(&usage.consumer)
}

/// The placement `record`'s consumers require, or `None` when it has no anchored consumers.
pub(crate) fn required_placement(
    record: &DeclarationRecord,
    usages: &UsagesByDeclaration<'_>,
    anchor_sets: &AnchorSets,
) -> Option<RequiredPlacement> {
    let declaration_usages: &[&PlacementUsage] = usages
        .get(&record.identity)
        .map(Vec::as_slice)
        .unwrap_or_default();
    if record.scope == ScopeKind::Private {
        let direct: bool = declaration_usages
            .iter()
            .any(|usage| owner_uses_directly(record, usage));
        let path: String = record
            .owning_path
            .clone()
            .filter(|path| !path.is_empty())
            .unwrap_or_else(|| record.ownership_root.path.clone());
        return direct.then_some(RequiredPlacement {
            scope: ScopeKind::Private,
            path: Some(path),
            consumers: Vec::new(),
        });
    }
    if declaration_usages.is_empty() {
        return None;
    }
    let anchors: &HashSet<Anchor> = anchor_sets.get(&record.identity)?;
    if anchors.is_empty() {
        return None;
    }
    let consumers: Vec<String> = declaration_usages
        .iter()
        .map(|usage| consumer_label(usage))
        .collect::<BTreeSet<String>>()
        .into_iter()
        .collect();
    let global = |consumers: Vec<String>| RequiredPlacement {
        scope: ScopeKind::Global,
        path: None,
        consumers,
    };
    let roots: HashSet<&OwnershipRoot> = anchors.iter().map(|(root, _)| root).collect();
    let single_root: Option<&OwnershipRoot> = match roots.iter().next() {
        Some(root) if roots.len() == 1 && root.kind != OwnershipRootKind::Global => Some(root),
        _ => None,
    };
    let Some(ownership_root) = single_root else {
        return Some(global(consumers));
    };
    let distinct: HashSet<&str> = anchors.iter().map(|(_, path)| path.as_str()).collect();
    if let [required_path] = distinct.iter().copied().collect::<Vec<&str>>().as_slice() {
        if is_named_kind(record.identity.kind) && *required_path == ownership_root.path {
            return Some(global(consumers));
        }
        let scope: ScopeKind = if record.identity.kind == DeclarationKind::SingularAudit {
            ScopeKind::Inherited
        } else {
            ScopeKind::Local
        };
        return Some(RequiredPlacement {
            scope,
            path: Some((*required_path).to_owned()),
            consumers,
        });
    }
    let paths: Vec<&str> = anchors.iter().map(|(_, path)| path.as_str()).collect();
    let required_path: String = common_prefix(&paths);
    if required_path == ownership_root.path {
        return Some(global(consumers));
    }
    Some(RequiredPlacement {
        scope: ScopeKind::Inherited,
        path: Some(required_path),
        consumers,
    })
}

/// `_consumer_label`: the consumer, and what it uses the declaration through.
fn consumer_label(usage: &PlacementUsage) -> String {
    let mut label: String = format_identity(&usage.consumer);
    if let Some(through) = &usage.through {
        label.push_str(" through ");
        label.push_str(&format_identity(through));
    }
    label
}
