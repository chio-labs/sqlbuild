//! One query's view of a lookup: records, values and every mapping Python's `ScopeLookup` keys.

use std::cell::OnceCell;
use std::collections::HashMap;

use crate::placement::main::required_declaration_placements::required_declaration_placements;
use crate::placement::models::{PlacementIndex, PlacementUsage, RequiredPlacement};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, KeyedGroups, OwnershipRoot, QualifiedIdentity,
    ReportGrant, ReportUsage, ResourceIdentity, ResourceRecord,
};
use crate::scope_report::models::{Completeness, DeclarationValues, ReportSource};

/// Each group's members by the key of its first member.
fn keyed<K: std::hash::Hash + Eq>(
    groups: &KeyedGroups,
    key: impl Fn(usize) -> K,
) -> HashMap<K, &[usize]> {
    groups
        .groups
        .iter()
        .map(|group| (key(group[0]), group.as_slice()))
        .collect()
}

/// The lookup mappings of one query, keyed as Python's dictionaries are.
pub(crate) struct Context<'a> {
    pub(crate) source: ReportSource<'a>,
    resources_by_path: HashMap<&'a str, &'a [usize]>,
    declarations: HashMap<&'a DeclarationIdentity, &'a [usize]>,
    usages_by_consumer: HashMap<&'a QualifiedIdentity, &'a [usize]>,
    usages_by_declaration: HashMap<&'a DeclarationIdentity, &'a [usize]>,
    grants_by_resource: HashMap<&'a ResourceIdentity, &'a [usize]>,
    /// Every grant of each declaration, in the index's canonical grant order.
    grants_by_declaration: HashMap<&'a DeclarationIdentity, Vec<usize>>,
    placements: OnceCell<HashMap<DeclarationIdentity, RequiredPlacement>>,
}

impl<'a> Context<'a> {
    pub(crate) fn new(source: ReportSource<'a>) -> Self {
        let records = source.records;
        let groups = &source.lookup.groups;
        let mut grants_by_declaration: HashMap<&'a DeclarationIdentity, Vec<usize>> =
            HashMap::new();
        for grant in &source.lookup.grants {
            grants_by_declaration
                .entry(&records.grants[*grant].declaration)
                .or_default()
                .push(*grant);
        }
        Self {
            source,
            resources_by_path: keyed(&groups.resources_by_path, |member| {
                source.lookup.resource_paths[member].as_str()
            }),
            declarations: keyed(&groups.declarations, |member| {
                &records.declarations[member].identity
            }),
            usages_by_consumer: keyed(&groups.usages_by_consumer, |member| {
                &records.usages[member].consumer
            }),
            usages_by_declaration: keyed(&groups.usages_by_declaration, |member| {
                &records.usages[member].declaration
            }),
            grants_by_resource: keyed(&groups.grants_by_resource, |member| {
                &records.grants[member].resource
            }),
            grants_by_declaration,
            placements: OnceCell::new(),
        }
    }

    pub(crate) fn completeness(&self) -> Completeness {
        self.source.values.completeness
    }

    pub(crate) fn declaration(&self, position: usize) -> &'a DeclarationRecord {
        &self.source.records.declarations[position]
    }

    pub(crate) fn resource(&self, position: usize) -> &'a ResourceRecord {
        &self.source.records.resources[position]
    }

    pub(crate) fn values(&self, position: usize) -> Option<&'a DeclarationValues> {
        self.source.values.declarations.get(position)
    }

    pub(crate) fn usage(&self, position: usize) -> &'a ReportUsage {
        &self.source.records.usages[position]
    }

    pub(crate) fn grant(&self, position: usize) -> &'a ReportGrant {
        &self.source.records.grants[position]
    }

    /// The index's declarations in canonical order, as input positions.
    pub(crate) fn canonical_declarations(&self) -> &'a [usize] {
        &self.source.lookup.declarations
    }

    /// The index's ownership roots in canonical order.
    pub(crate) fn canonical_roots(&self) -> impl Iterator<Item = &'a OwnershipRoot> + 'a {
        let records = self.source.records;
        self.source
            .lookup
            .roots
            .iter()
            .map(move |position| &records.roots[*position])
    }

    /// The index's resources in canonical order.
    pub(crate) fn canonical_resources(&self) -> impl Iterator<Item = &'a ResourceRecord> + 'a {
        let records = self.source.records;
        self.source
            .lookup
            .resources
            .iter()
            .map(move |position| &records.resources[*position])
    }

    pub(crate) fn declarations_of(&self, identity: &DeclarationIdentity) -> &'a [usize] {
        self.declarations.get(identity).copied().unwrap_or_default()
    }

    pub(crate) fn resources_at(&self, path: &str) -> &'a [usize] {
        self.resources_by_path
            .get(path)
            .copied()
            .unwrap_or_default()
    }

    pub(crate) fn usages_of_consumer(&self, consumer: &QualifiedIdentity) -> &'a [usize] {
        self.usages_by_consumer
            .get(consumer)
            .copied()
            .unwrap_or_default()
    }

    pub(crate) fn usages_of_declaration(&self, declaration: &DeclarationIdentity) -> &'a [usize] {
        self.usages_by_declaration
            .get(declaration)
            .copied()
            .unwrap_or_default()
    }

    pub(crate) fn grants_of_resource(&self, resource: &ResourceIdentity) -> &'a [usize] {
        self.grants_by_resource
            .get(resource)
            .copied()
            .unwrap_or_default()
    }

    pub(crate) fn grants_of_declaration(&self, declaration: &DeclarationIdentity) -> &[usize] {
        self.grants_by_declaration
            .get(declaration)
            .map(Vec::as_slice)
            .unwrap_or_default()
    }

    /// Whether the usage-complete index's consumers require a placement of `identity`.
    pub(crate) fn required_placement(
        &self,
        identity: &DeclarationIdentity,
    ) -> Option<&RequiredPlacement> {
        self.placements
            .get_or_init(|| required_declaration_placements(&self.placement_index()))
            .get(identity)
    }

    /// The canonical index as placement reads it.
    fn placement_index(&self) -> PlacementIndex {
        let records = self.source.records;
        let lookup = self.source.lookup;
        PlacementIndex {
            resources: lookup
                .resources
                .iter()
                .map(|position| records.resources[*position].clone())
                .collect(),
            declarations: lookup
                .declarations
                .iter()
                .map(|position| records.declarations[*position].clone())
                .collect(),
            usages: lookup
                .usages
                .iter()
                .map(|position| {
                    let usage = &records.usages[*position];
                    PlacementUsage {
                        consumer: usage.consumer.clone(),
                        declaration: usage.declaration.clone(),
                        through: usage.through.clone(),
                    }
                })
                .collect(),
        }
    }
}
