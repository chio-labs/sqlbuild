//! Project-wide inputs compared outside the cached base snapshot: Python dependency files.

use pyo3::prelude::{PyResult, Python};
use sqlbuild_analysis::definition_changes::constants::{
    DEFINITION_ASPECT, DEPENDENCIES_KIND, PROJECT_NODE_NAME,
};
use sqlbuild_analysis::definition_changes::main::definition_digest::definition_digest;
use sqlbuild_analysis::definition_changes::main::node_key::node_key;
use sqlbuild_analysis::definition_changes::models::{DefinitionSnapshot, NodeDefinition};
use sqlbuild_core::git_revisions::main::base_dependency_files::base_dependency_files;
use sqlbuild_core::git_revisions::main::current_dependency_files::current_dependency_files;
use sqlbuild_core::git_revisions::models::GitBase;

use crate::bindings::_helpers::change_selection::base_snapshot::git_error;

fn add_dependencies(
    snapshot: &DefinitionSnapshot,
    files: &[(String, String)],
) -> DefinitionSnapshot {
    let parts: Vec<&str> = files
        .iter()
        .flat_map(|(path, text)| [path.as_str(), text.as_str()])
        .collect();
    let mut updated: DefinitionSnapshot = snapshot.clone();
    updated.nodes.insert(
        node_key(DEPENDENCIES_KIND, PROJECT_NODE_NAME),
        NodeDefinition {
            kind: DEPENDENCIES_KIND.to_owned(),
            name: PROJECT_NODE_NAME.to_owned(),
            aspects: [(DEFINITION_ASPECT.to_owned(), definition_digest(&parts))].into(),
            ..NodeDefinition::default()
        },
    );
    updated
}

/// `snapshot` of the base revision with its dependency files.
pub(crate) fn with_base_dependencies(
    py: Python<'_>,
    base: &GitBase,
    snapshot: &DefinitionSnapshot,
) -> PyResult<DefinitionSnapshot> {
    let files: Vec<(String, String)> = py
        .detach(|| base_dependency_files(base))
        .map_err(|error| git_error(py, error))?;
    Ok(add_dependencies(snapshot, &files))
}

/// `snapshot` of the working tree with its dependency files.
pub(crate) fn with_current_dependencies(
    py: Python<'_>,
    base: &GitBase,
    snapshot: &DefinitionSnapshot,
) -> PyResult<DefinitionSnapshot> {
    let files: Vec<(String, String)> = py
        .detach(|| current_dependency_files(base))
        .map_err(|error| git_error(py, error))?;
    Ok(add_dependencies(snapshot, &files))
}
