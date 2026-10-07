//! Read and parse the unscoped SQL files below one root in parallel, in Python's order.

use crate::_helpers::pool::discovery_pool;
use crate::_helpers::reading::{read_authored_text, undecodable_path_failure};
use crate::_helpers::scoped_paths::is_in_scoped_declaration_tree;
use crate::constants::SQL_FILE_SUFFIX;
use crate::models::{DiscoveredFile, DiscoveryFailure, FileOutcome, ProjectRoot, StageFailure};
use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;
use rayon::iter::{IntoParallelIterator, ParallelIterator};

/// Every unscoped `*.sql` file below `directory`, read and handed to `parse`.
pub(crate) fn discover_sql_files<T: Send>(
    root: &ProjectRoot,
    tree: &ProjectTree,
    directory: &str,
    parse: impl Fn(&str, String) -> Result<T, DiscoveryFailure> + Sync,
) -> Result<Vec<DiscoveredFile<T>>, StageFailure> {
    let pool = discovery_pool().map_err(StageFailure::Internal)?;
    pool.install(|| {
        let paths: Vec<String> = rglob(tree, directory, |entry| {
            entry.name.ends_with(SQL_FILE_SUFFIX)
        })?;
        Ok(paths
            .into_par_iter()
            .filter(|relative_path| !is_in_scoped_declaration_tree(relative_path))
            .map(|relative_path| DiscoveredFile {
                outcome: read_and_parse(root, tree, &relative_path, &parse),
                relative_path,
            })
            .collect())
    })
}

fn read_and_parse<T>(
    root: &ProjectRoot,
    tree: &ProjectTree,
    relative_path: &str,
    parse: &impl Fn(&str, String) -> Result<T, DiscoveryFailure>,
) -> FileOutcome<T> {
    if let Some(failure) = undecodable_path_failure(root, tree, relative_path) {
        return FileOutcome::Failed(failure);
    }
    match read_authored_text(&tree.absolute(relative_path)) {
        Ok(contents) => match parse(&root.display_path(relative_path), contents) {
            Ok(parsed) => FileOutcome::Parsed(parsed),
            Err(failure) => FileOutcome::Failed(failure),
        },
        Err(failure) => FileOutcome::Unreadable(failure),
    }
}
