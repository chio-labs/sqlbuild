//! `project_import_closure`: the project modules one Python file imports, transitively.

use std::path::{Path, PathBuf};

use crate::rule_evidence::_helpers::closure::module_closure;
use crate::rule_evidence::_helpers::paths::resolve;

/// Every module and package initializer under `project_dir` that `source_path` executes, sorted.
///
/// Imports resolve from the project directory, the way project Python imports `macros.currency`
/// or `python._helpers`; standard-library and installed modules are not part of the closure.
pub fn project_import_closure(
    source_path: &Path,
    project_dir: &Path,
    python_version: (u8, u8),
) -> Vec<PathBuf> {
    let root: PathBuf = resolve(project_dir);
    module_closure(&resolve(source_path), (&root, &root), None, python_version)
}
