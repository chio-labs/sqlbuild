//! The `*.py` files below `functions/python/`, read as Python reads them.

use crate::declaration_files::_helpers::listing::collections::{
    ListedFile, matches_python_glob, read_files,
};
use crate::declaration_files::constants::PYTHON_FUNCTIONS_ROOT;
use crate::models::{DiscoveredFile, ProjectRoot, StageFailure};
use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;

/// Every Python function file in sorted path order, with its text or read failure.
pub fn python_function_files(
    root: &ProjectRoot,
    tree: &ProjectTree,
) -> Result<Vec<DiscoveredFile<String>>, StageFailure> {
    let files: Vec<ListedFile> = rglob(tree, PYTHON_FUNCTIONS_ROOT, |entry| {
        matches_python_glob(&entry.name)
    })?
    .into_iter()
    .map(|relative_path| (relative_path, None))
    .collect();
    Ok(read_files(root, tree, files, |_, _, contents| Ok(contents))
        .into_iter()
        .map(|scoped| scoped.file)
        .collect())
}
