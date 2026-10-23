//! The local modules one Python module executes through its imports, transitively.

use std::collections::BTreeSet;
use std::convert::Infallible;
use std::path::{Path, PathBuf};

use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;

use crate::cpython_tree::main::parse_cpython_module::parse_cpython_module;
use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::{CpythonNode, ParsedSource};
use crate::rule_evidence::_helpers::imports::read_source;
use crate::rule_evidence::_helpers::paths::{local_import_paths, package_inits};

/// Every module and package initializer under `root` that `source_path` executes, sorted.
pub(crate) fn module_closure(
    source_path: &Path,
    (project, root): (&Path, &Path),
    package: Option<&str>,
    python_version: (u8, u8),
) -> Vec<PathBuf> {
    let mut helpers: BTreeSet<PathBuf> = BTreeSet::new();
    let Ok(()) = breadth_first_reach([source_path.to_path_buf()], None, &mut helpers, |current| {
        let mut candidates: BTreeSet<PathBuf> = package_inits(current, root).into_iter().collect();
        let parsed: Option<ParsedSource> =
            parse_cpython_module(&read_source(current), python_version);
        if let Some(parsed) = &parsed {
            let roots: Vec<CpythonNode<'_>> =
                parsed.module.body.iter().map(CpythonNode::Stmt).collect();
            for node in walk_breadth_first(roots) {
                candidates.extend(local_import_paths(&node, current, (project, root), package));
            }
        }
        candidates.remove(source_path);
        Ok::<_, Infallible>(candidates)
    });
    helpers.into_iter().collect()
}
