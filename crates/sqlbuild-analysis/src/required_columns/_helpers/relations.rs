//! The external columns each local relation's output columns stand for.

use std::rc::Rc;

use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::required_columns::models::ColumnRead;

/// `_RelationReads`: named output slots, and resources whose every column passes through.
#[derive(Clone, Debug, Default)]
pub(crate) struct RelationReads {
    pub(crate) slots: Vec<(String, Vec<ColumnRead>)>,
    pub(crate) passthrough: Vec<(String, String)>,
}

impl RelationReads {
    /// Whether the relation has `column_name`, and the reads it stands for.
    pub(crate) fn resolve_with_presence(&self, column_name: &str) -> (bool, Vec<ColumnRead>) {
        let normalized: String = python_casefold(column_name);
        if let Some((_, leaves)) = self
            .slots
            .iter()
            .rev()
            .find(|(name, _)| python_casefold(name) == normalized)
        {
            return (true, leaves.clone());
        }
        let leaves: Vec<ColumnRead> = self
            .passthrough
            .iter()
            .map(|(resource_type, resource_name)| ColumnRead {
                resource_type: resource_type.clone(),
                resource_name: resource_name.clone(),
                column_name: column_name.to_owned(),
            })
            .collect();
        (!self.passthrough.is_empty(), leaves)
    }

    pub(crate) fn resolve(&self, column_name: &str) -> Vec<ColumnRead> {
        self.resolve_with_presence(column_name).1
    }
}

/// A Python dict of relations by casefolded name: insertion-ordered, replaced in place.
#[derive(Clone, Debug, Default)]
pub(crate) struct RelationMap {
    entries: Vec<(String, Rc<RelationReads>)>,
}

impl RelationMap {
    pub(crate) fn get(&self, name: &str) -> Option<&Rc<RelationReads>> {
        self.entries
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, relation)| relation)
    }

    pub(crate) fn insert(&mut self, name: String, relation: Rc<RelationReads>) {
        match self.entries.iter_mut().find(|(key, _)| *key == name) {
            Some(entry) => entry.1 = relation,
            None => self.entries.push((name, relation)),
        }
    }

    /// `{**self, **other}`.
    pub(crate) fn merged(&self, other: &Self) -> Self {
        let mut merged: Self = self.clone();
        for (name, relation) in &other.entries {
            merged.insert(name.clone(), Rc::clone(relation));
        }
        merged
    }

    /// `_unique_relations`: each distinct relation once, in first-seen order.
    pub(crate) fn unique(&self) -> Vec<Rc<RelationReads>> {
        let mut unique: Vec<Rc<RelationReads>> = Vec::new();
        for (_, relation) in &self.entries {
            if !unique.iter().any(|seen| Rc::ptr_eq(seen, relation)) {
                unique.push(Rc::clone(relation));
            }
        }
        unique
    }
}

/// `relation.get(name) or other.get(name)` with `name` casefolded.
pub(crate) fn either<'a>(
    local: &'a RelationMap,
    outer: &'a RelationMap,
    name: &str,
) -> Option<&'a Rc<RelationReads>> {
    let key: String = python_casefold(name);
    local.get(&key).or_else(|| outer.get(&key))
}

/// `_deduplicated_sources`.
pub(crate) fn unique_reads(reads: Vec<ColumnRead>) -> Vec<ColumnRead> {
    let mut unique: Vec<ColumnRead> = Vec::with_capacity(reads.len());
    for read in reads {
        if !unique.contains(&read) {
            unique.push(read);
        }
    }
    unique
}

/// `_deduplicated_resources`.
pub(crate) fn unique_resources(resources: Vec<(String, String)>) -> Vec<(String, String)> {
    let mut unique: Vec<(String, String)> = Vec::with_capacity(resources.len());
    for resource in resources {
        if !unique.contains(&resource) {
            unique.push(resource);
        }
    }
    unique
}
