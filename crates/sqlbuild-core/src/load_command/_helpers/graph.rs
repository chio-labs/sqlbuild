//! Loader graph lookups: dependencies, closures and execution order.

use std::collections::{BTreeSet, HashMap};

use crate::load_command::models::LoadGraph;

/// Indexed views of a load graph, as the Python dictionaries keyed them.
pub(crate) struct GraphIndex {
    /// Managed source name to its loader; a later duplicate wins.
    pub(crate) source_loader: HashMap<String, String>,
    /// Managed source names in declaration order, first occurrence only.
    pub(crate) source_order: Vec<String>,
    /// Loader name to its dependencies; a later duplicate wins.
    pub(crate) upstream: HashMap<String, Vec<String>>,
    /// Loader name to its sources in declaration order.
    pub(crate) sources_by_loader: HashMap<String, Vec<String>>,
}

impl GraphIndex {
    pub(crate) fn new(graph: &LoadGraph) -> Self {
        let mut source_loader: HashMap<String, String> = HashMap::new();
        let mut source_order: Vec<String> = Vec::new();
        for (name, loader) in &graph.sources {
            if source_loader.insert(name.clone(), loader.clone()).is_none() {
                source_order.push(name.clone());
            }
        }
        let mut sources_by_loader: HashMap<String, Vec<String>> = HashMap::new();
        for name in &source_order {
            sources_by_loader
                .entry(source_loader[name].clone())
                .or_default()
                .push(name.clone());
        }
        Self {
            source_loader,
            source_order,
            upstream: graph.loaders.iter().cloned().collect(),
            sources_by_loader,
        }
    }

    pub(crate) fn is_loader(&self, name: &str) -> bool {
        self.upstream.contains_key(name)
    }

    pub(crate) fn dependencies(&self, loader: &str) -> &[String] {
        self.upstream.get(loader).map_or(&[], Vec::as_slice)
    }

    /// The loader and every loader it transitively depends on.
    pub(crate) fn upstream_closure(&self, loader: &str) -> BTreeSet<String> {
        let mut closure: BTreeSet<String> = BTreeSet::new();
        let mut pending: Vec<String> = vec![loader.to_owned()];
        while let Some(next) = pending.pop() {
            if closure.insert(next.clone()) {
                pending.extend(self.dependencies(&next).iter().cloned());
            }
        }
        closure
    }

    /// The loader, every loader depending on it transitively, and all their sources.
    pub(crate) fn downstream_closure(&self, loader: &str) -> (BTreeSet<String>, BTreeSet<String>) {
        let mut loaders: BTreeSet<String> = BTreeSet::new();
        let mut pending: Vec<String> = vec![loader.to_owned()];
        while let Some(next) = pending.pop() {
            if !loaders.insert(next.clone()) {
                continue;
            }
            for (candidate, dependencies) in &self.upstream {
                if dependencies.contains(&next) {
                    pending.push(candidate.clone());
                }
            }
        }
        let sources: BTreeSet<String> = loaders
            .iter()
            .flat_map(|name| {
                self.sources_by_loader
                    .get(name)
                    .into_iter()
                    .flatten()
                    .cloned()
            })
            .collect();
        (loaders, sources)
    }

    /// `names` ordered dependencies first, visiting in sorted order.
    pub(crate) fn topological_order(&self, names: &BTreeSet<String>) -> Vec<String> {
        let mut ordered: Vec<String> = Vec::new();
        let mut visited: BTreeSet<String> = BTreeSet::new();
        for name in names {
            self.visit(name, names, (&mut ordered, &mut visited));
        }
        ordered
    }

    fn visit(
        &self,
        name: &str,
        names: &BTreeSet<String>,
        (ordered, visited): (&mut Vec<String>, &mut BTreeSet<String>),
    ) {
        if !visited.insert(name.to_owned()) {
            return;
        }
        for dependency in self.dependencies(name) {
            if names.contains(dependency) {
                self.visit(dependency, names, (ordered, visited));
            }
        }
        ordered.push(name.to_owned());
    }
}
