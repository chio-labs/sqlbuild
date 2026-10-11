//! Python's `build_visibility_index`, `_visible_positions` and `_visibility_reason`.

use crate::scope_index::_helpers::paths::{
    canonical_ancestors, checked_path, is_canonical_descendant, normalize_path, parent,
};
use crate::scope_index::constants::{
    CURRENT_PATH_COMPONENT, PATH_RESOURCE_PREFIX, PATH_RESOURCE_SUFFIX,
};
use crate::scope_index::models::{
    DeclarationRecord, InaccessibleReason, RejectedPath, ResourceIdentity, ResourceRecord,
    ScopeDeferral, ScopeIndex, VisibilityGroups, VisibilityReason,
};
use crate::scope_index::models::{DeclaredScope, ResourceKind, ScopeKind};
use std::collections::HashMap;
use std::hash::Hash;

/// Canonical declaration positions per key, keys in first-occurrence order.
struct OrderedPositions<K> {
    entries: Vec<(K, Vec<usize>)>,
    lookup: HashMap<K, usize>,
}

impl<K: Hash + Eq + Clone> OrderedPositions<K> {
    fn new() -> Self {
        Self {
            entries: Vec::new(),
            lookup: HashMap::new(),
        }
    }

    fn push(&mut self, key: K, position: usize) {
        match self.lookup.get(&key) {
            Some(entry) => self.entries[*entry].1.push(position),
            None => {
                self.lookup.insert(key.clone(), self.entries.len());
                self.entries.push((key, vec![position]));
            }
        }
    }

    fn get(&self, key: &K) -> &[usize] {
        self.lookup
            .get(key)
            .map_or(&[], |entry| self.entries[*entry].1.as_slice())
    }

    fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

/// Canonical declaration positions grouped by the scope facts that make them visible.
pub(crate) struct VisibilityIndex {
    global: Vec<usize>,
    private: OrderedPositions<ResourceIdentity>,
    local: OrderedPositions<String>,
    inherited: OrderedPositions<String>,
}

impl VisibilityIndex {
    /// Python's `build_visibility_index` over the canonical declarations.
    pub(crate) fn build(index: &ScopeIndex) -> Result<Self, ScopeDeferral> {
        let mut visibility: Self = Self {
            global: Vec::new(),
            private: OrderedPositions::new(),
            local: OrderedPositions::new(),
            inherited: OrderedPositions::new(),
        };
        for (position, declaration_index) in index.canonical_declarations.iter().enumerate() {
            let declaration: &DeclarationRecord = &index.declarations[*declaration_index];
            match declaration.scope {
                ScopeKind::Global => visibility.global.push(position),
                ScopeKind::Private => {
                    if let Some(owner) = &declaration.identity.owner {
                        visibility.private.push(owner.clone(), position);
                    }
                }
                ScopeKind::Local => visibility.local.push(owner_path(declaration)?, position),
                ScopeKind::Inherited => {
                    visibility
                        .inherited
                        .push(owner_path(declaration)?, position);
                }
            }
        }
        Ok(visibility)
    }

    /// Python's `_visible_positions`: canonical positions a resource sees, in position order.
    pub(crate) fn visible_positions(
        &self,
        resource: &ResourceRecord,
    ) -> Result<Vec<usize>, ScopeDeferral> {
        let mut positions: Vec<usize> = self.global.clone();
        positions.extend_from_slice(self.private.get(&resource.identity));
        if !self.local.is_empty() || !self.inherited.is_empty() {
            let folder: String = parent(&resource.path)?;
            positions.extend_from_slice(self.local.get(&folder));
            for ancestor in canonical_ancestors(&folder) {
                positions.extend_from_slice(self.inherited.get(&ancestor.to_owned()));
            }
        }
        positions.sort_unstable();
        Ok(positions)
    }

    /// The positions as Python's `DeclarationVisibilityIndex` mappings hold them.
    pub(crate) fn groups(&self) -> VisibilityGroups {
        VisibilityGroups {
            global: self.global.clone(),
            private: self.private.entries.clone(),
            local: self.local.entries.clone(),
            inherited: self.inherited.entries.clone(),
        }
    }
}

/// Python's `_visibility_reason(...) is not None` for a synthetic path resource.
pub(crate) fn path_visibility(
    declaration: &DeclarationRecord,
    path_resource: &ResourceIdentity,
    folder: &str,
) -> Result<bool, ScopeDeferral> {
    scope_visibility(
        &DeclaredScope {
            scope: declaration.scope,
            owner: declaration.identity.owner.clone(),
            owning_path: declaration.owning_path.clone(),
        },
        path_resource,
        folder,
    )
}

/// Python's `path_visibility_reason(...) is not None` for an authored consumer path.
pub(crate) fn authored_path_visibility(
    declared: &DeclaredScope,
    path: &str,
) -> Result<bool, ScopeDeferral> {
    let normalized: String = normalize_path(path)?;
    let path_resource: ResourceIdentity = ResourceIdentity {
        kind: ResourceKind::Model,
        name: format!("{PATH_RESOURCE_PREFIX}{normalized}{PATH_RESOURCE_SUFFIX}"),
    };
    scope_visibility(declared, &path_resource, &parent(&normalized)?)
}

fn scope_visibility(
    declared: &DeclaredScope,
    path_resource: &ResourceIdentity,
    folder: &str,
) -> Result<bool, ScopeDeferral> {
    Ok(match declared.scope {
        ScopeKind::Global => true,
        ScopeKind::Private => declared.owner.as_ref() == Some(path_resource),
        ScopeKind::Local => folder == owner_folder(declared.owning_path.as_deref())?,
        ScopeKind::Inherited => {
            is_canonical_descendant(folder, &owner_folder(declared.owning_path.as_deref())?)
        }
    })
}

/// Python's `_declaration_owner`.
fn owner_path(declaration: &DeclarationRecord) -> Result<String, ScopeDeferral> {
    owner_folder(declaration.owning_path.as_deref())
}

fn owner_folder(owning_path: Option<&str>) -> Result<String, ScopeDeferral> {
    normalize_path(
        owning_path
            .filter(|path| !path.is_empty())
            .unwrap_or(CURRENT_PATH_COMPONENT),
    )
}

/// Python's `_visibility_reason` of a declaration for a resource, with checked paths.
pub(crate) fn visibility_reason(
    declaration: &DeclarationRecord,
    resource: &ResourceRecord,
) -> Result<Option<VisibilityReason>, RejectedPath> {
    match declaration.scope {
        ScopeKind::Global => return Ok(Some(VisibilityReason::Global)),
        ScopeKind::Private => {
            return Ok(
                (declaration.identity.owner.as_ref() == Some(&resource.identity))
                    .then_some(VisibilityReason::PrivateOwner),
            );
        }
        ScopeKind::Local | ScopeKind::Inherited => {}
    }
    let owner: String = checked_owner(declaration)?;
    let folder: String = checked_parent(&resource.path)?;
    Ok(match declaration.scope {
        ScopeKind::Local => (folder == owner).then_some(VisibilityReason::LocalOwner),
        _ => {
            is_canonical_descendant(&folder, &owner).then_some(VisibilityReason::InheritedAncestor)
        }
    })
}

/// Python's `_inaccessible_reason` of a declaration a resource cannot see.
pub(crate) fn inaccessible_reason(
    declaration: &DeclarationRecord,
    resource: &ResourceRecord,
) -> Result<InaccessibleReason, RejectedPath> {
    match declaration.scope {
        ScopeKind::Private => return Ok(InaccessibleReason::PrivateOwner),
        ScopeKind::Local => return Ok(InaccessibleReason::LocalBoundary),
        ScopeKind::Global | ScopeKind::Inherited => {}
    }
    let owner: String = checked_owner(declaration)?;
    let folder: String = checked_parent(&resource.path)?;
    Ok(if is_canonical_descendant(&owner, &folder) {
        InaccessibleReason::DescendantScope
    } else if declaration.ownership_root.path == resource.ownership_root.path {
        InaccessibleReason::SiblingScope
    } else {
        InaccessibleReason::UnrelatedScope
    })
}

/// Python's `_declaration_owner`, or the owning path it rejects.
pub(crate) fn checked_owner(declaration: &DeclarationRecord) -> Result<String, RejectedPath> {
    checked_path(
        declaration
            .owning_path
            .as_deref()
            .filter(|path| !path.is_empty())
            .unwrap_or(CURRENT_PATH_COMPONENT),
    )
}

fn checked_parent(path: &str) -> Result<String, RejectedPath> {
    let normalized: String = checked_path(path)?;
    Ok(match normalized.rfind('/') {
        Some(index) => normalized[..index].to_owned(),
        None => CURRENT_PATH_COMPONENT.to_owned(),
    })
}
