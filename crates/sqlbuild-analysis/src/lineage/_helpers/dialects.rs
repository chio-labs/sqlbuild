//! The polyglot dialects SQLBuild's parser build carries.

use polyglot_sql::DialectType;

/// Whether SQLBuild's polyglot build carries `dialect`; the wheel carries every dialect.
pub(crate) fn is_compiled_dialect(dialect: DialectType) -> bool {
    matches!(
        dialect,
        DialectType::Generic
            | DialectType::PostgreSQL
            | DialectType::BigQuery
            | DialectType::Snowflake
            | DialectType::DuckDB
            | DialectType::TSQL
            | DialectType::Databricks
    )
}
