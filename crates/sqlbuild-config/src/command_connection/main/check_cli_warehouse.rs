//! Validate a `--warehouse` value.

use sqlbuild_core::text::main::python_str_repr::python_str_repr;
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::command_connection::_helpers::identifiers::is_warehouse_identifier;
use crate::command_connection::constants::WAREHOUSE_ERROR_CODE;
use crate::command_connection::errors::CommandConnectionError;

/// Reject an empty or malformed `--warehouse` identifier.
pub fn check_cli_warehouse(cli_warehouse: &str) -> Result<(), CommandConnectionError> {
    if python_strip(cli_warehouse).is_empty() {
        return Err(CommandConnectionError::User {
            code: Some(WAREHOUSE_ERROR_CODE),
            message: "--warehouse requires a warehouse name".to_owned(),
            help: Some("pass a name such as `--warehouse ADHOC_WH`, or omit the flag".to_owned()),
        });
    }
    if is_warehouse_identifier(cli_warehouse) {
        return Ok(());
    }
    Err(CommandConnectionError::User {
        code: Some(WAREHOUSE_ERROR_CODE),
        message: format!(
            "--warehouse {} is not a valid Snowflake warehouse identifier",
            python_str_repr(cli_warehouse)
        ),
        help: Some(
            "pass an unquoted identifier such as `--warehouse ADHOC_WH`, or a double-quoted identifier such as `--warehouse '\"Adhoc WH\"'`"
                .to_owned(),
        ),
    })
}
