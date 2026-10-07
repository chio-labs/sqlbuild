//! Discover, read and parse the SQL model files under `models/`.

use crate::_helpers::pool::discovery_pool;
use crate::_helpers::reading::{read_authored_text, undecodable_path_failure};
use crate::_helpers::scoped_paths::is_in_scoped_declaration_tree;
use crate::constants::{MODELS_DIRECTORY, SQL_FILE_SUFFIX};
use crate::model_files::_helpers::parsing::parse_model_file;
use crate::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use crate::models::{DiscoveredFile, FileOutcome, ProjectRoot, StageFailure};
use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;
use rayon::iter::{IntoParallelIterator, ParallelIterator};

/// Every model file in Python's discovery order, each parsed or carrying its first failure.
pub fn discover_model_files(
    root: &ProjectRoot,
    tree: &ProjectTree,
    options: &ModelFileOptions,
) -> Result<Vec<DiscoveredFile<DiscoveredModelFile>>, StageFailure> {
    let pool = discovery_pool().map_err(StageFailure::Internal)?;
    pool.install(|| {
        let paths: Vec<String> = rglob(tree, MODELS_DIRECTORY, |entry| {
            entry.name.ends_with(SQL_FILE_SUFFIX)
        })?;
        Ok(paths
            .into_par_iter()
            .filter(|relative_path| !is_in_scoped_declaration_tree(relative_path))
            .map(|relative_path| DiscoveredFile {
                outcome: discover_one(root, tree, &relative_path, options),
                relative_path,
            })
            .collect())
    })
}

fn discover_one(
    root: &ProjectRoot,
    tree: &ProjectTree,
    relative_path: &str,
    options: &ModelFileOptions,
) -> FileOutcome<DiscoveredModelFile> {
    if let Some(failure) = undecodable_path_failure(root, tree, relative_path) {
        return FileOutcome::Failed(failure);
    }
    let contents: String = match read_authored_text(&tree.absolute(relative_path)) {
        Ok(contents) => contents,
        Err(failure) => return FileOutcome::Unreadable(failure),
    };
    match parse_model_file(&root.display_path(relative_path), contents, options) {
        Ok(model_file) => FileOutcome::Parsed(model_file),
        Err(failure) => FileOutcome::Failed(failure),
    }
}
