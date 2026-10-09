//! The polyglot dialect Python's `dialect or "generic"` names, if this parser build carries it.

use polyglot_sql::DialectType;

/// Python's `parse_one(dialect=dialect or "generic")` dialect, if this parser build carries it.
pub fn parser_dialect(name: Option<&str>) -> Option<DialectType> {
    let name = name.filter(|name| !name.is_empty()).unwrap_or("generic");
    let Ok(dialect) = name.parse::<DialectType>() else {
        return None;
    };
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
    .then_some(dialect)
}
