//! Applying load selectors and excludes to the selected source and loader sets.

use std::collections::BTreeSet;
use std::convert::Infallible;

use crate::graph_walk::main::breadth_first_reach::breadth_first_reach;
use crate::load_command::_helpers::graph::GraphIndex;
use crate::load_command::constants::UPSTREAM_MARK;
use crate::load_command::errors::UnknownLoadSelector;

/// Selected sources and loaders, and the loaders selected by name.
#[derive(Default)]
pub(crate) struct Selection {
    pub(crate) sources: BTreeSet<String>,
    pub(crate) loaders: BTreeSet<String>,
    pub(crate) direct_loaders: BTreeSet<String>,
    pub(crate) excluded_loaders: BTreeSet<String>,
}

/// The selector name and whether it asks for upstream and downstream nodes.
fn parse(selector: &str) -> (String, bool, bool) {
    let stripped: &str = selector.trim();
    (
        stripped.trim_matches(UPSTREAM_MARK).to_owned(),
        stripped.starts_with(UPSTREAM_MARK),
        stripped.ends_with(UPSTREAM_MARK),
    )
}

fn validate(index: &GraphIndex, name: &str) -> Result<(), UnknownLoadSelector> {
    if index.source_loader.contains_key(name) || index.is_loader(name) {
        return Ok(());
    }
    Err(UnknownLoadSelector {
        name: name.to_owned(),
    })
}

/// The loader a downstream selector starts from.
fn downstream_root<'a>(index: &'a GraphIndex, name: &'a str) -> &'a str {
    if index.is_loader(name) {
        return name;
    }
    &index.source_loader[name]
}

impl Selection {
    fn add_loader(&mut self, index: &GraphIndex, (loader, upstream): (&str, bool)) {
        self.loaders.insert(loader.to_owned());
        if upstream {
            self.loaders.extend(index.upstream_closure(loader));
        }
    }

    fn select_name(&mut self, index: &GraphIndex, (name, upstream): (&str, bool)) {
        if let Some(loader) = index.source_loader.get(name) {
            self.sources.insert(name.to_owned());
            self.add_loader(index, (loader, upstream));
        } else if let Some(sources) = index.sources_by_loader.get(name) {
            self.sources.extend(sources.iter().cloned());
            self.add_loader(index, (name, upstream));
        } else if index.is_loader(name) {
            self.direct_loaders.insert(name.to_owned());
            self.add_loader(index, (name, upstream));
        }
    }

    /// Apply each selector in order.
    pub(crate) fn select(
        &mut self,
        index: &GraphIndex,
        selectors: &[String],
    ) -> Result<(), UnknownLoadSelector> {
        for selector in selectors {
            let (name, upstream, downstream) = parse(selector);
            validate(index, &name)?;
            self.select_name(index, (&name, upstream));
            if downstream {
                let (loaders, sources) = index.downstream_closure(downstream_root(index, &name));
                self.loaders.extend(loaders);
                self.sources.extend(sources);
            }
        }
        Ok(())
    }

    fn exclude_name(&mut self, index: &GraphIndex, name: &str) {
        if let Some(loader) = index.source_loader.get(name) {
            self.sources.remove(name);
            let still_used: bool = index
                .sources_by_loader
                .get(loader)
                .into_iter()
                .flatten()
                .any(|source| self.sources.contains(source));
            if !still_used {
                self.loaders.remove(loader);
            }
        } else if let Some(sources) = index.sources_by_loader.get(name) {
            for source in sources {
                self.sources.remove(source);
            }
            self.loaders.remove(name);
            self.excluded_loaders.insert(name.to_owned());
        } else if index.is_loader(name) {
            self.loaders.remove(name);
            self.excluded_loaders.insert(name.to_owned());
        }
    }

    /// Apply each exclude in order.
    pub(crate) fn exclude(
        &mut self,
        index: &GraphIndex,
        excludes: &[String],
    ) -> Result<(), UnknownLoadSelector> {
        for selector in excludes {
            let (name, _, downstream) = parse(selector);
            validate(index, &name)?;
            self.exclude_name(index, &name);
            if downstream {
                let (loaders, sources) = index.downstream_closure(downstream_root(index, &name));
                self.loaders.retain(|loader| !loaders.contains(loader));
                self.sources.retain(|source| !sources.contains(source));
            }
        }
        Ok(())
    }

    /// Whether a dependency of `loader` is unselected and blocked.
    fn has_blocked_dependency(
        &self,
        index: &GraphIndex,
        (loader, blocked): (&str, &BTreeSet<String>),
    ) -> bool {
        for dependency in index.dependencies(loader) {
            if !self.loaders.contains(dependency) && blocked.contains(dependency) {
                return true;
            }
        }
        false
    }

    /// Drop loaders whose dependency was excluded or dropped, and the sources they run.
    pub(crate) fn prune_missing_dependencies(&mut self, index: &GraphIndex) {
        let mut blocked: BTreeSet<String> = self.excluded_loaders.clone();
        loop {
            let missing: Vec<String> = self
                .loaders
                .iter()
                .filter(|loader| self.has_blocked_dependency(index, (loader, &blocked)))
                .cloned()
                .collect();
            let orphaned: Vec<String> = self
                .sources
                .iter()
                .filter(|source| !self.loaders.contains(&index.source_loader[*source]))
                .cloned()
                .collect();
            if missing.is_empty() && orphaned.is_empty() {
                return;
            }
            for loader in missing {
                self.loaders.remove(&loader);
                blocked.insert(loader);
            }
            for source in orphaned {
                self.sources.remove(&source);
            }
        }
    }

    /// Keep only loaders a selected source or a by-name loader needs.
    pub(crate) fn prune_unneeded_loaders(&mut self, index: &GraphIndex) {
        let mut needed: BTreeSet<String> = self.direct_loaders.clone();
        for source in &self.sources {
            let loader: &String = &index.source_loader[source];
            if self.loaders.contains(loader) {
                needed.insert(loader.clone());
            }
        }
        let starts: Vec<String> = needed.iter().cloned().collect();
        let Ok(()) = breadth_first_reach(starts, None, &mut needed, |loader| {
            Ok::<_, Infallible>(
                index
                    .dependencies(loader)
                    .iter()
                    .filter(|dependency| self.loaders.contains(*dependency))
                    .cloned(),
            )
        });
        self.loaders.retain(|loader| needed.contains(loader));
    }
}
