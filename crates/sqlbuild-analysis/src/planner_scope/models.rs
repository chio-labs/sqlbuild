//! Ordered loader facts used by planner scope resolution.

use std::collections::{HashMap, HashSet, VecDeque};

use crate::assembly::project::types::ObjectKey;
use crate::planner_scope::constants::SOURCE;

/// Loader dependencies resolved from Python function objects at the boundary.
#[derive(Debug, Default)]
pub struct LoaderGraph {
    pub loaders: HashMap<String, Vec<String>>,
    pub sources: Vec<(String, Option<String>)>,
}

impl LoaderGraph {
    /// Upstream loader names in breadth-first, first-seen order.
    pub fn upstream(&self, dependencies: &[String]) -> Vec<String> {
        let mut pending: VecDeque<String> = dependencies.iter().cloned().collect();
        let mut seen: HashSet<String> = HashSet::new();
        let mut names: Vec<String> = Vec::new();
        while let Some(name) = pending.pop_front() {
            if !seen.insert(name.clone()) {
                continue;
            }
            if let Some(dependencies) = self.loaders.get(&name) {
                pending.extend(dependencies.iter().cloned());
            }
            names.push(name);
        }
        names
    }

    /// Source key for a loader, using the last source declaration for that loader.
    pub fn key(&self, loader: &str) -> ObjectKey {
        let name = self.sources.iter().rev().find_map(|(name, source_loader)| {
            (source_loader.as_deref() == Some(loader)).then_some(name.as_str())
        });
        ("source".to_owned(), name.unwrap_or(loader).to_owned())
    }

    /// Managed loader name for a source key.
    pub fn source_loader(&self, key: &ObjectKey) -> Option<&str> {
        if key.0 != SOURCE {
            return None;
        }
        self.sources
            .iter()
            .rev()
            .find_map(|(name, loader)| (name == &key.1).then_some(loader.as_deref()))
            .flatten()
    }

    /// Whether a loader is intermediate rather than attached to a declared source.
    pub fn intermediate(&self, name: &str) -> bool {
        self.loaders.contains_key(name)
            && !self
                .sources
                .iter()
                .any(|(_, loader)| loader.as_deref() == Some(name))
    }
}
