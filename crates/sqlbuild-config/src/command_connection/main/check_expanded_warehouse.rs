//! Validate a target group's warehouse after template expansion.

use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::command_connection::_helpers::identifiers::is_warehouse_identifier;
use crate::command_connection::constants::{SETTING_SNIPPET_INDENT, WAREHOUSE_ERROR_CODE};
use crate::command_connection::errors::CommandConnectionError;
use crate::command_connection::models::AuthoredWarehouse;

/// Reject an expanded group warehouse that is not a Snowflake identifier.
pub fn check_expanded_warehouse(
    authored: &AuthoredWarehouse,
    warehouse: &str,
) -> Result<(), CommandConnectionError> {
    if is_warehouse_identifier(warehouse) {
        return Ok(());
    }
    let section: String = format!("targets.{}.warehouses", authored.target_name);
    Err(CommandConnectionError::User {
        code: Some(WAREHOUSE_ERROR_CODE),
        message: format!(
            "{} [{section}] {} resolves to {}, which is not a valid Snowflake warehouse identifier",
            authored.file_name,
            authored.group,
            python_str_repr(warehouse)
        ),
        help: Some(format!(
            "to use an unquoted identifier (or a double-quoted one such as \"Adhoc WH\"), set this in {}:\n{SETTING_SNIPPET_INDENT}[{section}]\n{SETTING_SNIPPET_INDENT}{} = \"ADHOC_WH\"",
            authored.file_name, authored.group
        )),
    })
}
