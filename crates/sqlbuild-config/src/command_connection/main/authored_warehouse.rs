//! The authored warehouse a target sets for a command group.

use crate::command_connection::constants::LOCAL_CONFIG_FILENAME;
use crate::command_connection::models::AuthoredWarehouse;
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;

/// The local target's group warehouse, else the project target's, with the file that sets it.
#[must_use]
pub fn authored_warehouse(
    (target_name, group): (&str, &str),
    local_value: Option<String>,
    project_value: Option<String>,
) -> Option<AuthoredWarehouse> {
    let (warehouse, file_name) = match (local_value, project_value) {
        (Some(local), _) => (local, LOCAL_CONFIG_FILENAME),
        (None, Some(project)) => (project, PROJECT_CONFIG_FILENAME),
        (None, None) => return None,
    };
    Some(AuthoredWarehouse {
        warehouse,
        target_name: target_name.to_owned(),
        group: group.to_owned(),
        file_name: file_name.to_owned(),
    })
}
