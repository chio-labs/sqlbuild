//! The unscoped model `schema.yml` files and seed declaration files, in Python's order.

use crate::_helpers::scoped_paths::is_in_scoped_declaration_tree;
use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;
use crate::yaml_files::_helpers::suffixes::name_matches;
use crate::yaml_files::constants::{
    MODELS_DIRECTORY, SCHEMA_FILE_NAME, SEED_DECLARATION_PATTERN, SEEDS_DIRECTORY,
    UNSUPPORTED_SEED_DECLARATION_PATTERN,
};
use crate::yaml_files::models::YamlPathFailure;

fn matching(tree: &ProjectTree, root: &str, pattern: &str) -> Result<Vec<String>, YamlPathFailure> {
    rglob(tree, root, |entry| name_matches(&entry.name, pattern)).map_err(YamlPathFailure::Stage)
}

/// Python's `schema_file_paths`; a `.yaml` seed declaration fails as a schema error.
pub fn schema_yaml_paths(tree: &ProjectTree) -> Result<Vec<String>, YamlPathFailure> {
    let mut paths: Vec<String> = Vec::new();
    if tree.is_dir(MODELS_DIRECTORY) {
        paths.extend(
            matching(tree, MODELS_DIRECTORY, SCHEMA_FILE_NAME)?
                .into_iter()
                .filter(|path| !is_in_scoped_declaration_tree(path)),
        );
    }
    if tree.is_dir(SEEDS_DIRECTORY) {
        if let Some(path) =
            matching(tree, SEEDS_DIRECTORY, UNSUPPORTED_SEED_DECLARATION_PATTERN)?.first()
        {
            return Err(YamlPathFailure::YamlSeedDeclaration(path.clone()));
        }
        paths.extend(matching(tree, SEEDS_DIRECTORY, SEED_DECLARATION_PATTERN)?);
    }
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    paths.retain(|path| seen.insert(path.clone()));
    Ok(paths)
}
