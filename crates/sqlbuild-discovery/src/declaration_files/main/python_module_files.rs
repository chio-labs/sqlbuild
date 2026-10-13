//! The `*.py` module files below one project directory, as Python module discovery lists them.

use crate::declaration_files::_helpers::listing::collections::matches_python_glob;
use crate::declaration_files::_helpers::listing::module_paths::is_listed_module;
use crate::models::StageFailure;
use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;

/// Sorted `*.py` paths below `root` without `__init__` modules, or any `_`-prefixed part if public.
pub fn python_module_files(
    tree: &ProjectTree,
    root: &str,
    public_only: bool,
) -> Result<Vec<String>, StageFailure> {
    let mut paths: Vec<String> = rglob(tree, root, |entry| matches_python_glob(&entry.name))?;
    paths.retain(|relative_path| is_listed_module(relative_path, root, public_only));
    Ok(paths)
}
