//! The grant resolver behind Python's expected-model and tested-macro relationship grants.

use crate::scope_index::_helpers::paths::{normalize_path, parent};
use crate::scope_index::_helpers::visibility::{VisibilityIndex, path_visibility};
use crate::scope_index::constants::{
    CURRENT_PATH_COMPONENT, MACRO_TEST_LEXICAL_FILE, PATH_RESOURCE_PREFIX, PATH_RESOURCE_SUFFIX,
};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationKind, DeclarationRecord, GrantKind, GrantRecord, GrantThrough,
    RelationshipFact, ResourceIdentity, ResourceKind, ScopeDeferral, ScopeIndex, ScopeKind,
};
use std::collections::{HashMap, HashSet};

/// Grants in order, each first occurrence kept as Python's `dict.fromkeys` does.
pub(crate) fn unique_grants(index: &ScopeIndex, grants: Vec<GrantRecord>) -> Vec<GrantRecord> {
    let mut seen: HashSet<GrantKey<'_>> = HashSet::new();
    let unique: Vec<bool> = grants
        .iter()
        .map(|grant| seen.insert(grant_key(index, grant)))
        .collect();
    drop(seen);
    grants
        .into_iter()
        .zip(unique)
        .filter_map(|(grant, unique)| unique.then_some(grant))
        .collect()
}

type GrantKey<'a> = (
    &'a ResourceIdentity,
    &'a DeclarationIdentity,
    GrantThroughKey<'a>,
    GrantKind,
);

#[derive(PartialEq, Eq, Hash)]
enum GrantThroughKey<'a> {
    Model(&'a str),
    Declaration(&'a DeclarationIdentity),
}

fn grant_key<'a>(index: &'a ScopeIndex, grant: &'a GrantRecord) -> GrantKey<'a> {
    (
        &grant.resource,
        &index.declarations[grant.declaration].identity,
        match &grant.through {
            GrantThrough::Model(name) => GrantThroughKey::Model(name),
            GrantThrough::Declaration(declaration) => {
                GrantThroughKey::Declaration(&index.declarations[*declaration].identity)
            }
        },
        grant.kind,
    )
}

/// Visibility and identity lookups over one index, as the Python grant functions use them.
pub(crate) struct GrantResolver<'a> {
    index: &'a ScopeIndex,
    visibility: VisibilityIndex,
    /// Canonical resource records per identity.
    resources: HashMap<&'a ResourceIdentity, Vec<usize>>,
    /// The first canonical declaration record per identity.
    first_declarations: HashMap<&'a DeclarationIdentity, usize>,
}

impl<'a> GrantResolver<'a> {
    pub(crate) fn new(index: &'a ScopeIndex) -> Result<Self, ScopeDeferral> {
        let mut resources: HashMap<&ResourceIdentity, Vec<usize>> = HashMap::new();
        for resource in &index.canonical_resources {
            resources
                .entry(&index.resources[*resource].identity)
                .or_default()
                .push(*resource);
        }
        let mut first_declarations: HashMap<&DeclarationIdentity, usize> = HashMap::new();
        for declaration in &index.canonical_declarations {
            first_declarations
                .entry(&index.declarations[*declaration].identity)
                .or_insert(*declaration);
        }
        Ok(Self {
            index,
            visibility: VisibilityIndex::build(index)?,
            resources,
            first_declarations,
        })
    }

    /// Python's `resolve_declaration_visibility(...).visible` as first declaration records.
    fn visible_declarations(
        &self,
        resource: &ResourceIdentity,
    ) -> Result<Vec<usize>, ScopeDeferral> {
        let mut visible: Vec<usize> = Vec::new();
        for record in self.resources.get(resource).map_or(&[][..], Vec::as_slice) {
            for position in self
                .visibility
                .visible_positions(&self.index.resources[*record])?
            {
                let identity: &DeclarationIdentity =
                    &self.index.declarations[self.index.canonical_declarations[position]].identity;
                visible.push(self.first_declarations[identity]);
            }
        }
        Ok(visible)
    }

    /// Python's `_expected_model_grants` for one fact.
    pub(crate) fn expected_model_grants(
        &self,
        fact: &RelationshipFact,
    ) -> Result<Vec<GrantRecord>, ScopeDeferral> {
        let called: HashSet<&str> = fact.called_macros.iter().map(String::as_str).collect();
        let mut grants: Vec<GrantRecord> = Vec::new();
        for model_name in &fact.expected_models {
            let through: ResourceIdentity = ResourceIdentity {
                kind: ResourceKind::Model,
                name: model_name.clone(),
            };
            for declaration in self.visible_declarations(&through)? {
                let record: &DeclarationRecord = &self.index.declarations[declaration];
                if record.scope == ScopeKind::Private
                    || (record.identity.kind == DeclarationKind::Macro
                        && !called.contains(record.identity.name.as_str()))
                {
                    continue;
                }
                grants.push(GrantRecord {
                    resource: fact.resource.clone(),
                    declaration,
                    through: GrantThrough::Model(model_name.clone()),
                    kind: GrantKind::ExpectedModel,
                });
            }
        }
        Ok(grants)
    }

    /// Python's `_tested_macro_grants` for one fact.
    pub(crate) fn tested_macro_grants(
        &self,
        fact: &RelationshipFact,
    ) -> Result<Vec<GrantRecord>, ScopeDeferral> {
        if fact.tested_macros.is_empty() {
            return Ok(Vec::new());
        }
        let directly_visible: HashSet<&DeclarationIdentity> = self
            .visible_declarations(&fact.resource)?
            .into_iter()
            .map(|declaration| &self.index.declarations[declaration].identity)
            .collect();
        let mut grants: Vec<GrantRecord> = Vec::new();
        for macro_name in &fact.tested_macros {
            let identity: DeclarationIdentity = DeclarationIdentity {
                kind: DeclarationKind::Macro,
                name: macro_name.clone(),
                owner: None,
            };
            let Some(tested_macro) = self.first_declarations.get(&identity).copied() else {
                continue;
            };
            let owning_path: &str = self.index.declarations[tested_macro]
                .owning_path
                .as_deref()
                .filter(|path| !path.is_empty())
                .unwrap_or(CURRENT_PATH_COMPONENT);
            let lexical_path: String =
                normalize_path(&format!("{owning_path}/{MACRO_TEST_LEXICAL_FILE}"))?;
            let path_resource: ResourceIdentity = ResourceIdentity {
                kind: ResourceKind::Model,
                name: format!("{PATH_RESOURCE_PREFIX}{lexical_path}{PATH_RESOURCE_SUFFIX}"),
            };
            let folder: String = parent(&lexical_path)?;
            for declaration in &self.index.canonical_declarations {
                let record: &DeclarationRecord = &self.index.declarations[*declaration];
                if !path_visibility(record, &path_resource, &folder)?
                    || record.scope == ScopeKind::Private
                    || directly_visible.contains(&record.identity)
                {
                    continue;
                }
                grants.push(GrantRecord {
                    resource: fact.resource.clone(),
                    declaration: *declaration,
                    through: GrantThrough::Declaration(tested_macro),
                    kind: GrantKind::TestedMacro,
                });
            }
        }
        Ok(grants)
    }
}
