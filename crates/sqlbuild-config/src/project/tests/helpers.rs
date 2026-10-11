use crate::project::errors::{ConfigFailure, FailureClass, LoadFailure, MessagePiece};
use crate::project::main::load_local_config::load_local_config;
use crate::project::main::load_project_config::load_project_config;
use crate::project::models::{ConfigFile, ConfigPaths};
use tempfile::TempDir;

/// A project directory with `project` and `local` files, and its config paths.
pub(super) fn project_directory(project: &str, local: &str) -> (TempDir, ConfigPaths) {
    let directory = TempDir::new().expect("temporary directory");
    std::fs::write(directory.path().join("sqlbuild_project.toml"), project).expect("project");
    std::fs::write(directory.path().join("sqlbuild_local.toml"), local).expect("local");
    let paths = ConfigPaths {
        project: directory.path().join("sqlbuild_project.toml"),
        legacy_project: directory.path().join("sqlbuild_project.yml"),
        local: directory.path().join("sqlbuild_local.toml"),
        legacy_local: directory.path().join("sqlbuild_local.yml"),
    };
    (directory, paths)
}

/// The first rejection of loading both files, if any.
pub(super) fn first_failure(paths: &ConfigPaths) -> Option<ConfigFailure> {
    [
        load_project_config(paths).err(),
        load_local_config(paths).err(),
    ]
    .into_iter()
    .flatten()
    .find_map(LoadFailure::into_config_failure)
}

/// A rejection whose message starts with the path of `file`.
pub(super) fn failure_at(
    file: ConfigFile,
    text: &str,
    help: Option<&str>,
) -> Option<ConfigFailure> {
    Some(ConfigFailure {
        message: vec![
            MessagePiece::File(file),
            MessagePiece::Text(format!(" {text}")),
        ],
        help: help.map(str::to_owned),
        class: FailureClass::ProjectConfig,
    })
}
