//! `run_cursor`: the opaque cursor of one projected run.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::execution_history::_helpers::base64url::encode;
use crate::execution_history::_helpers::dialects::run_cursor_prefix;
use crate::execution_history::_helpers::timestamps::{default_text, stored_text};
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::{Dialect, RunRow};

/// The prefix and URL-safe base64 of compact ASCII JSON `[namespace, created_at, run_id]`.
pub fn run_cursor(dialect: Dialect, namespace: &str, run: &RunRow) -> Result<String, HistoryError> {
    let created_at: String = match dialect {
        Dialect::Sqlite => stored_text(&run.created_at),
        Dialect::Postgres => default_text(&run.created_at),
    };
    let payload = JsonValue::Array(vec![
        JsonValue::String(namespace.to_owned()),
        JsonValue::String(created_at),
        JsonValue::String(run.run_id.clone()),
    ]);
    let options = StdlibJsonOptions::new(None).with_separators(",", ":");
    let text: String = dumps(&payload, &JsonDialect::Stdlib(options))
        .map_err(|error| HistoryError::new(HistoryErrorKind::Storage, format!("{error:?}")))?;
    Ok(format!(
        "{}{}",
        run_cursor_prefix(dialect),
        encode(text.as_bytes())
    ))
}
