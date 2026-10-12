//! Shared pieces of the conflict checks: the error, name tables and the duplicate scan.

use std::collections::HashMap;

use crate::models::{DiscoveryFailure, FailureKind};
use crate::project_validation::models::{NamedPath, NodeFact, ProjectFacts, ValidationFailure};

/// A `DiscoveryConflictError` with this message.
pub(crate) fn conflict(message: String) -> ValidationFailure {
    DiscoveryFailure::new(FailureKind::Conflict, message).into()
}

/// Every schema seed declaration with the schema file that declares it.
pub(crate) fn schema_seeds(facts: &ProjectFacts) -> Vec<NamedPath> {
    let mut seeds: Vec<NamedPath> = Vec::new();
    for schema in &facts.schemas {
        for seed in &schema.seeds {
            seeds.push(named(&seed.name, &schema.path));
        }
    }
    seeds
}

/// Every source entry with the source file that declares it.
pub(crate) fn source_entries(facts: &ProjectFacts) -> Vec<NamedPath> {
    let mut entries: Vec<NamedPath> = Vec::new();
    for file in &facts.sources {
        for entry in &file.entries {
            entries.push(named(&entry.name, &file.path));
        }
    }
    entries
}

pub(crate) fn named(name: &str, path: &str) -> NamedPath {
    NamedPath {
        name: name.to_owned(),
        path: path.to_owned(),
    }
}

pub(crate) fn node_path(node: &NodeFact) -> NamedPath {
    named(&node.name, &node.path)
}

/// Reject the second of two entries with the same name.
pub(crate) fn unique_named(
    entries: &[impl std::borrow::Borrow<NamedPath>],
    message: impl Fn(&str, &str, &str) -> String,
) -> Result<(), ValidationFailure> {
    let mut seen: HashMap<&str, &str> = HashMap::new();
    for entry in entries {
        let entry: &NamedPath = entry.borrow();
        if let Some(existing) = seen.get(entry.name.as_str()) {
            return Err(conflict(message(&entry.name, existing, &entry.path)));
        }
        seen.insert(&entry.name, &entry.path);
    }
    Ok(())
}
