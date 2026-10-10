//! The polyglot dialect Python's `dialect or "generic"` names, if this parser build carries it.

use polyglot_sql::DialectType;

/// Python's `parse_one(dialect=dialect or "generic")` dialect, if this parser build carries it.
pub fn parser_dialect(name: Option<&str>) -> Option<DialectType> {
    let name = name.filter(|name| !name.is_empty()).unwrap_or("generic");
    let Ok(dialect) = name.parse::<DialectType>() else {
        return None;
    };
    is_compiled_dialect(dialect).then_some(dialect)
}

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
