//! Dialect names: Python's `TypeDialect` coercion.

use crate::type_system::models::TypeDialect;

/// Python's `_coerce_type_dialect`: an exact `TypeDialect` value, otherwise None.
pub(crate) fn coerce_type_dialect(name: &str) -> Option<TypeDialect> {
    Some(match name {
        "generic" => TypeDialect::Generic,
        "bigquery" => TypeDialect::BigQuery,
        "snowflake" => TypeDialect::Snowflake,
        "duckdb" => TypeDialect::DuckDb,
        "motherduck" => TypeDialect::MotherDuck,
        "databricks" => TypeDialect::Databricks,
        "postgres" => TypeDialect::Postgres,
        "tsql" => TypeDialect::Tsql,
        _ => return None,
    })
}
