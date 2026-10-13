//! The YAML files directly below `sources/`, as Python's source discovery lists them.

use crate::models::StageFailure;
use crate::tree::main::children::children;
use crate::tree::models::ProjectTree;
use crate::yaml_files::_helpers::suffixes::python_suffix;
use crate::yaml_files::constants::{SOURCES_DIRECTORY, YAML_FILE_SUFFIXES};

/// `sorted(path for path in sources.iterdir() if path.suffix in YAML_FILE_SUFFIXES)`.
pub fn source_yaml_paths(tree: &ProjectTree) -> Result<Vec<String>, StageFailure> {
    if !tree.is_dir(SOURCES_DIRECTORY) {
        return Ok(Vec::new());
    }
    Ok(children(tree, SOURCES_DIRECTORY)?
        .into_iter()
        .filter(|(_, entry)| YAML_FILE_SUFFIXES.contains(&python_suffix(&entry.name)))
        .map(|(path, _)| path)
        .collect())
}
