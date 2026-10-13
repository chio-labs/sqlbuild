//! The error for a warehouse command with no configured connection.

use crate::command_connection::errors::CommandConnectionError;

/// The error naming `project_file` and, when one is selected, the target without a connection.
#[must_use]
pub fn missing_connection_error(
    project_file: &str,
    target_name: Option<&str>,
) -> CommandConnectionError {
    CommandConnectionError::ProjectConfig(match target_name {
        None => format!(
            "{project_file} no target is selected and no top-level [connection] is configured; add [connections.<name>] and a [targets.<name>] that uses it, then set default_target or pass --target"
        ),
        Some(target) => format!(
            "{project_file} target {target} has no connection; add [connections.<name>] (or set connection = \"<name>\" on [targets.{target}]) in sqlbuild_project.toml or sqlbuild_local.toml"
        ),
    })
}
