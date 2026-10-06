//! Function names a dialect recognises as built-ins, from the SQL library's own metadata.

use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use crate::sql_tokens::constants::CALL_SYNTAX_FUNCTIONS;
use polyglot_sql::{Dialect, DialectType, Expression};
use polyglot_sql_function_catalogs::types::{builtin_arity, type_signature};
use polyglot_sql_function_catalogs::{
    CatalogSink, FunctionNameCase, FunctionSignature, register_enabled_catalogs,
};

const DUCKDB_CATALOG: &str = "duckdb";

static CATALOG_FUNCTIONS: LazyLock<HashMap<&'static str, HashSet<String>>> = LazyLock::new(|| {
    let mut sink = NameSink::default();
    register_enabled_catalogs(&mut sink);
    sink.names
});
static SNOWFLAKE_TYPED: LazyLock<HashSet<String>> =
    LazyLock::new(|| parser_typed_names(DialectType::Snowflake));
static BIGQUERY_TYPED: LazyLock<HashSet<String>> =
    LazyLock::new(|| parser_typed_names(DialectType::BigQuery));
static POSTGRES_TYPED: LazyLock<HashSet<String>> =
    LazyLock::new(|| parser_typed_names(DialectType::PostgreSQL));
static DATABRICKS_TYPED: LazyLock<HashSet<String>> =
    LazyLock::new(|| parser_typed_names(DialectType::Databricks));
static TSQL_TYPED: LazyLock<HashSet<String>> =
    LazyLock::new(|| parser_typed_names(DialectType::TSQL));
static GENERIC_TYPED: LazyLock<HashSet<String>> =
    LazyLock::new(|| parser_typed_names(DialectType::Generic));

/// Return whether `upper_name(...)` calls a function the dialect defines.
pub(crate) fn is_builtin_function(dialect: DialectType, upper_name: &str) -> bool {
    if CALL_SYNTAX_FUNCTIONS.contains(&upper_name) {
        return true;
    }
    let lower_name = upper_name.to_ascii_lowercase();
    let typed = match dialect {
        DialectType::DuckDB => return catalogued(DUCKDB_CATALOG, &lower_name),
        DialectType::Snowflake => &SNOWFLAKE_TYPED,
        DialectType::BigQuery => &BIGQUERY_TYPED,
        DialectType::PostgreSQL => &POSTGRES_TYPED,
        DialectType::Databricks => &DATABRICKS_TYPED,
        DialectType::TSQL => &TSQL_TYPED,
        _ => &GENERIC_TYPED,
    };
    typed.contains(&lower_name) || catalogued(catalog_key(dialect), &lower_name)
}

/// Every catalogued or parser-typed built-in function name of `dialect`, lower-cased.
#[cfg(test)]
pub(crate) fn builtin_function_names(dialect: DialectType) -> Vec<String> {
    let typed: &HashSet<String> = match dialect {
        DialectType::DuckDB => &HashSet::new(),
        DialectType::Snowflake => &SNOWFLAKE_TYPED,
        DialectType::BigQuery => &BIGQUERY_TYPED,
        DialectType::PostgreSQL => &POSTGRES_TYPED,
        DialectType::Databricks => &DATABRICKS_TYPED,
        DialectType::TSQL => &TSQL_TYPED,
        _ => &GENERIC_TYPED,
    };
    let key = match dialect {
        DialectType::DuckDB => DUCKDB_CATALOG,
        _ => catalog_key(dialect),
    };
    let catalogued = CATALOG_FUNCTIONS.get(key).into_iter().flatten();
    let mut names: Vec<String> = typed.iter().chain(catalogued).cloned().collect();
    names.sort_unstable();
    names.dedup();
    names
}

fn catalog_key(dialect: DialectType) -> &'static str {
    match dialect {
        DialectType::Snowflake => "snowflake",
        DialectType::BigQuery => "bigquery",
        DialectType::PostgreSQL => "postgres",
        _ => "",
    }
}

fn catalogued(key: &str, lower_name: &str) -> bool {
    CATALOG_FUNCTIONS
        .get(key)
        .is_some_and(|names| names.contains(lower_name))
        || builtin_arity(key, lower_name).is_some()
        || type_signature(key, lower_name).is_some()
}

/// Catalogued function names whose call the dialect's parser turns into a specific expression.
fn parser_typed_names(dialect: DialectType) -> HashSet<String> {
    let parser = Dialect::get(dialect);
    let mut typed: HashSet<String> = HashSet::new();
    for name in CATALOG_FUNCTIONS.get(DUCKDB_CATALOG).into_iter().flatten() {
        if is_typed_call(&parser, name) {
            typed.insert(name.clone());
        }
    }
    typed
}

fn is_typed_call(parser: &Dialect, lower_name: &str) -> bool {
    if !lower_name
        .chars()
        .all(|character| character.is_ascii_alphanumeric() || character == '_')
    {
        return false;
    }
    let Ok(statements) = parser.parse(&format!("SELECT {lower_name}(probe)")) else {
        return false;
    };
    let Some(Expression::Select(select)) = statements.first() else {
        return false;
    };
    select.expressions.first().is_some_and(|call| {
        !matches!(
            call,
            Expression::Function(_) | Expression::Anonymous(_) | Expression::Column(_)
        )
    })
}

#[derive(Default)]
struct NameSink {
    names: HashMap<&'static str, HashSet<String>>,
}

impl CatalogSink for NameSink {
    fn set_dialect_name_case(&mut self, _dialect: &'static str, _name_case: FunctionNameCase) {}

    fn set_function_name_case(
        &mut self,
        _dialect: &'static str,
        _function_name: &str,
        _name_case: FunctionNameCase,
    ) {
    }

    fn register(
        &mut self,
        dialect: &'static str,
        function_name: &str,
        _signatures: Vec<FunctionSignature>,
    ) {
        self.names
            .entry(dialect)
            .or_default()
            .insert(function_name.to_ascii_lowercase());
    }
}
