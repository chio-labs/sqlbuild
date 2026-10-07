//! Python's `build_visibility_index`, `_visible_positions` and `_visibility_reason`.

use crate::scope_index::_helpers::paths::{
    canonical_ancestors, is_canonical_descendant, normalize_path, parent,
};
use crate::scope_index::constants::CURRENT_PATH_COMPONENT;
use crate::scope_index::models::ScopeKind;
use crate::scope_index::models::{
    DeclarationRecord, ResourceIdentity, ResourceRecord, ScopeDeferral, ScopeIndex,
    VisibilityGroups,
};
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
    Ok(match declaration.scope {
        ScopeKind::Global => true,
        ScopeKind::Private => declaration.identity.owner.as_ref() == Some(path_resource),
        ScopeKind::Local => folder == owner_path(declaration)?,
        ScopeKind::Inherited => is_canonical_descendant(folder, &owner_path(declaration)?),
    })
}

/// Python's `_declaration_owner`.
fn owner_path(declaration: &DeclarationRecord) -> Result<String, ScopeDeferral> {
    normalize_path(
        declaration
            .owning_path
            .as_deref()
            .filter(|path| !path.is_empty())
            .unwrap_or(CURRENT_PATH_COMPONENT),
    )
}
