//! Dialect names: Polyglot's resolution and Python's `TypeDialect` coercion.

use polyglot_sql::{Dialect, DialectType};

use crate::type_system::models::TypeDialect;

/// The Polyglot dialect Python's wheel resolves `name` to, when this build includes it.
pub(crate) fn polyglot_dialect(name: &str) -> Option<Dialect> {
    let Ok(dialect_type) = name.parse::<DialectType>() else {
        return None;
    };
    matches!(
        dialect_type,
        DialectType::Generic
            | DialectType::PostgreSQL
            | DialectType::BigQuery
            | DialectType::Snowflake
            | DialectType::DuckDB
            | DialectType::TSQL
            | DialectType::Databricks
    )
    .then(|| Dialect::get(dialect_type))
}

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
