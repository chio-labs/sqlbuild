//! `import_closure`: the repository-owned helper modules one rule module imports.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use crate::cpython_tree::main::parse_cpython_module::parse_cpython_module;
use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::{CpythonNode, ParsedSource};
use crate::rule_evidence::_helpers::imports::read_source;
use crate::rule_evidence::_helpers::paths::{local_import_paths, package_inits, resolve};
use crate::rule_evidence::constants::RULES_DIRECTORY_NAME;

/// Every rules module and package initializer `source_path` executes, sorted; paths are resolved.
pub fn import_closure(
    source_path: &Path,
    project_dir: &Path,
    python_version: (u8, u8),
) -> Vec<PathBuf> {
    let rules_root: PathBuf = resolve(&project_dir.join(RULES_DIRECTORY_NAME));
    let mut pending: Vec<PathBuf> = vec![source_path.to_path_buf()];
    let mut visited: BTreeSet<PathBuf> = BTreeSet::from([source_path.to_path_buf()]);
    let mut helpers: BTreeSet<PathBuf> = BTreeSet::new();
    while let Some(current) = pending.pop() {
        let mut candidates: BTreeSet<PathBuf> =
            package_inits(&current, &rules_root).into_iter().collect();
        let source: Option<String> = read_source(&current);
        let parsed: Option<ParsedSource> =
            source.and_then(|source| parse_cpython_module(&source, python_version));
        if let Some(parsed) = &parsed {
            let roots: Vec<CpythonNode<'_>> =
                parsed.module.body.iter().map(CpythonNode::Stmt).collect();
            for node in walk_breadth_first(roots) {
                candidates.extend(local_import_paths(&node, &current, &rules_root));
            }
        }
        for candidate in candidates {
            if visited.insert(candidate.clone()) {
                helpers.insert(candidate.clone());
                pending.push(candidate);
            }
        }
    }
    helpers.into_iter().collect()
}
