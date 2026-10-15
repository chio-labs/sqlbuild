//! `validate_schema_target`: only the current schema version can be upgraded to.

use crate::execution_history::_helpers::schema::unsupported_version;
use crate::execution_history::constants::SCHEMA_VERSION;
use crate::execution_history::errors::HistoryError;
use crate::execution_history::models::Dialect;

/// Reject any target other than the current schema version.
pub fn validate_schema_target(dialect: Dialect, target: i64) -> Result<(), HistoryError> {
    if target == SCHEMA_VERSION {
        return Ok(());
    }
    Err(unsupported_version(dialect, target))
}
