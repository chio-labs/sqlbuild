//! `project_import_closure`: the project modules one Python file imports, transitively.

use std::path::{Path, PathBuf};

use crate::rule_evidence::_helpers::closure::module_closure;
use crate::rule_evidence::_helpers::paths::resolve;

/// Project modules and package initializers `source_path` imports, resolved from `project_dir`.
pub fn project_import_closure(
    source_path: &Path,
    project_dir: &Path,
    python_version: (u8, u8),
) -> Vec<PathBuf> {
    let root: PathBuf = resolve(project_dir);
    module_closure(&resolve(source_path), (&root, &root), None, python_version)
}
