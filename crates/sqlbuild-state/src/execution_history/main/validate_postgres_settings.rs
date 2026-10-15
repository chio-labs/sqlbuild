//! `validate_postgres_settings`: the PostgreSQL history DSN, timeouts and retry budget.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::execution_history::constants::{
    MIN_RETRIES, MIN_TIMEOUT, POSTGRES_MAX_CONNECT_TIMEOUT_SECONDS,
    POSTGRES_MAX_STATEMENT_TIMEOUT_MS, POSTGRES_MAX_TRANSACTION_RETRIES,
};
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::PostgresSettings;

fn storage_error(message: String) -> HistoryError {
    HistoryError::new(HistoryErrorKind::Storage, message)
}

/// A non-blank DSN, positive bounded timeouts and `0..=10` transaction retries.
pub fn validate_postgres_settings(settings: &PostgresSettings) -> Result<(), HistoryError> {
    if settings
        .dsn
        .as_deref()
        .is_none_or(|dsn| python_strip(dsn).is_empty())
    {
        return Err(storage_error(
            "PostgreSQL execution history requires an explicit secret-resolved DSN".to_owned(),
        ));
    }
    let timeouts = [
        ("connect_timeout_seconds", settings.connect_timeout_seconds),
        ("statement_timeout_ms", settings.statement_timeout_ms),
    ];
    for (name, value) in timeouts {
        if value.is_none_or(|value| value < MIN_TIMEOUT) {
            return Err(storage_error(format!("{name} must be a positive integer")));
        }
    }
    if settings
        .connect_timeout_seconds
        .is_some_and(|value| value > POSTGRES_MAX_CONNECT_TIMEOUT_SECONDS)
    {
        return Err(storage_error(format!(
            "connect_timeout_seconds must not exceed {POSTGRES_MAX_CONNECT_TIMEOUT_SECONDS}"
        )));
    }
    if settings
        .statement_timeout_ms
        .is_some_and(|value| value > POSTGRES_MAX_STATEMENT_TIMEOUT_MS)
    {
        return Err(storage_error(format!(
            "statement_timeout_ms must not exceed {POSTGRES_MAX_STATEMENT_TIMEOUT_MS}"
        )));
    }
    if settings
        .max_transaction_retries
        .is_none_or(|value| !(MIN_RETRIES..=POSTGRES_MAX_TRANSACTION_RETRIES).contains(&value))
    {
        return Err(storage_error(format!(
            "max_transaction_retries must be a non-negative integer no greater than \
             {POSTGRES_MAX_TRANSACTION_RETRIES}"
        )));
    }
    Ok(())
}
