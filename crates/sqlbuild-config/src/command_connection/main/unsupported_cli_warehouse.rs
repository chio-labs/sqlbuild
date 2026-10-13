//! `--warehouse` for an adapter without a session warehouse.

use crate::command_connection::constants::UNSUPPORTED_WAREHOUSE_CODE;
use crate::command_connection::errors::CommandConnectionError;

/// The error for a `--warehouse` the adapter cannot select.
#[must_use]
pub fn unsupported_cli_warehouse(
    cli_warehouse: &str,
    adapter_name: &str,
) -> CommandConnectionError {
    CommandConnectionError::User {
        code: Some(UNSUPPORTED_WAREHOUSE_CODE),
        message: format!(
            "--warehouse {cli_warehouse} was given, but the '{adapter_name}' adapter has no warehouse to select"
        ),
        help: Some(
            "remove --warehouse; it needs an adapter with a session warehouse, such as snowflake or an adapter extending it"
                .to_owned(),
        ),
    }
}
