//! Loader graph lookups: dependencies, closures and execution order.

use std::collections::{BTreeSet, HashMap};
use std::convert::Infallible;

use crate::graph_walk::main::breadth_first_reach::breadth_first_reach;
use crate::graph_walk::main::depth_first_postorder::depth_first_postorder;
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
        let mut closure: BTreeSet<String> = BTreeSet::from([loader.to_owned()]);
        let Ok(()) = breadth_first_reach([loader.to_owned()], None, &mut closure, |next| {
            Ok::<_, Infallible>(self.dependencies(next).iter().cloned())
        });
        closure
    }

    /// The loader, every loader depending on it transitively, and all their sources.
    pub(crate) fn downstream_closure(&self, loader: &str) -> (BTreeSet<String>, BTreeSet<String>) {
        let mut loaders: BTreeSet<String> = BTreeSet::from([loader.to_owned()]);
        let Ok(()) = breadth_first_reach([loader.to_owned()], None, &mut loaders, |next| {
            Ok::<_, Infallible>(
                self.upstream
                    .iter()
                    .filter(|(_, dependencies)| dependencies.contains(next))
                    .map(|(candidate, _)| candidate.clone())
                    .collect::<Vec<String>>(),
            )
        });
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
        depth_first_postorder(names.iter().cloned(), |name| {
            self.dependencies(name)
                .iter()
                .filter(|dependency| names.contains(*dependency))
                .cloned()
                .collect::<Vec<String>>()
        })
    }
}
