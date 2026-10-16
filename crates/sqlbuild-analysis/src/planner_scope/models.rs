//! Ordered loader facts used by planner scope resolution.

use std::collections::HashMap;
use std::convert::Infallible;

use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;
use sqlbuild_core::graph_walk::models::VisitOrder;
use sqlbuild_core::graph_walk::types::NodeSet;

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
        let mut names: VisitOrder<&String> = VisitOrder::default();
        for name in dependencies {
            let Ok(_) = names.insert_new(&name);
        }
        let Ok(()) = breadth_first_reach(dependencies, None, &mut names, |name| {
            Ok::<_, Infallible>(self.loaders.get(*name).into_iter().flatten())
        });
        names.order.into_iter().cloned().collect()
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
