//! Public compiler entry point for `@@` SQL interpolation.

use crate::compiler::models::{InterpolatedSql, InterpolationFailure};
use crate::compiler::types::InterpolationHost;
use sqlbuild_core::text::models::PythonText;

/// Interpolate `@@` tokens in `sql`, reading variables, environment and context from `host`.
pub fn interpolate_sql<H: InterpolationHost>(
    python: PythonText,
    host: &H,
    sql: &str,
    file_path: &str,
) -> Result<InterpolatedSql, InterpolationFailure> {
    crate::compiler::_helpers::sql_interpolation::substitution::interpolate(
        python, host, sql, file_path,
    )
}
