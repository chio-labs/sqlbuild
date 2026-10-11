//! Python's `normalize_sql_value`: validate one authored value into its canonical typed form.

use std::cell::Cell;

use crate::sql_values::_helpers::normalize::{Normalization, Place, normalize};
use crate::sql_values::errors::SqlValueFailure;
use crate::sql_values::models::{RawSqlValue, SqlValueLimits};
use sqlbuild_core::models::SqlValue;

/// The canonical value of `raw`, typed by `explicit_type` when given, under `limits`.
pub fn normalize_sql_value(
    raw: &RawSqlValue,
    context: &str,
    explicit_type: Option<&str>,
    limits: SqlValueLimits,
) -> Result<SqlValue, SqlValueFailure> {
    let state = Normalization {
        context,
        limits,
        elements: Cell::new(0),
        size: Cell::new(0),
    };
    normalize(raw, Place { path: "", depth: 1 }, &state, explicit_type)
}
