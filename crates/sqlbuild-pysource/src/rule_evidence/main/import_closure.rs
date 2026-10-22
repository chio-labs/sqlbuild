//! `import_closure`: the repository-owned helper modules one rule module imports.

use std::path::{Path, PathBuf};

use crate::rule_evidence::_helpers::closure::module_closure;
use crate::rule_evidence::_helpers::paths::resolve;
use crate::rule_evidence::constants::RULES_DIRECTORY_NAME;

/// Every rules module and package initializer `source_path` executes, sorted; paths are resolved.
pub fn import_closure(
    source_path: &Path,
    project_dir: &Path,
    python_version: (u8, u8),
) -> Vec<PathBuf> {
    let rules_root: PathBuf = resolve(&project_dir.join(RULES_DIRECTORY_NAME));
    let project: PathBuf = rules_root
        .parent()
        .map_or(PathBuf::new(), Path::to_path_buf);
    module_closure(
        source_path,
        (&project, &rules_root),
        Some(RULES_DIRECTORY_NAME),
        python_version,
    )
}
