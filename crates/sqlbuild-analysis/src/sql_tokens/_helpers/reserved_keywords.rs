//! Per-dialect reserved keywords, which can never be unquoted identifiers in that dialect.

use std::collections::HashSet;
use std::sync::LazyLock;

use polyglot_sql::DialectType;

static DUCKDB: LazyLock<HashSet<String>> =
    LazyLock::new(|| keyword_set(include_str!("../reserved_keywords/duckdb.txt")));
static POSTGRES: LazyLock<HashSet<String>> =
    LazyLock::new(|| keyword_set(include_str!("../reserved_keywords/postgres.txt")));
static BIGQUERY: LazyLock<HashSet<String>> =
    LazyLock::new(|| keyword_set(include_str!("../reserved_keywords/bigquery.txt")));
static SNOWFLAKE: LazyLock<HashSet<String>> =
    LazyLock::new(|| keyword_set(include_str!("../reserved_keywords/snowflake.txt")));
static TSQL: LazyLock<HashSet<String>> =
    LazyLock::new(|| keyword_set(include_str!("../reserved_keywords/tsql.txt")));
static DATABRICKS: LazyLock<HashSet<String>> =
    LazyLock::new(|| keyword_set(include_str!("../reserved_keywords/databricks.txt")));
static GENERIC: LazyLock<HashSet<String>> =
    LazyLock::new(|| keyword_set(include_str!("../reserved_keywords/generic.txt")));

/// Return whether the upper-cased word is a reserved keyword of `dialect`.
pub(crate) fn is_reserved_keyword(dialect: DialectType, upper_word: &str) -> bool {
    let keywords: &HashSet<String> = match dialect {
        DialectType::DuckDB => &DUCKDB,
        DialectType::PostgreSQL => &POSTGRES,
        DialectType::BigQuery => &BIGQUERY,
        DialectType::Snowflake => &SNOWFLAKE,
        DialectType::TSQL => &TSQL,
        DialectType::Databricks => &DATABRICKS,
        _ => &GENERIC,
    };
    keywords.contains(upper_word)
}

fn keyword_set(data: &str) -> HashSet<String> {
    data.lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .map(str::to_ascii_uppercase)
        .collect()
}
