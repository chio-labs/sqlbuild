//! Python's `resolve_binding_column`: the shape column an authored name binds to.

use crate::semantic_checks::_helpers::sql_text::text::{casefold, upper};

const QUOTE: char = '"';
const SNOWFLAKE: &str = "snowflake";
const CASE_SENSITIVE_DIALECTS: [&str; 2] = ["snowflake", "postgresql"];
/// `NATIVE_DIALECT_ALIASES`.
const DIALECT_ALIASES: [(&str, &str); 3] = [
    ("postgres", "postgresql"),
    ("motherduck", "duckdb"),
    ("sqlserver", "tsql"),
];
const GENERIC_DIALECT: &str = "generic";

/// The binding dialect Python's aliases map `dialect` to.
pub(crate) fn binding_dialect(dialect: Option<&str>) -> Option<&str> {
    let name = dialect.unwrap_or(GENERIC_DIALECT);
    match DIALECT_ALIASES.iter().find(|(alias, _)| *alias == name) {
        Some((_, target)) => Some(target),
        None => dialect,
    }
}

fn identity(value: &str, dialect: Option<&str>, ignore_quoted_case: bool) -> String {
    let quoted = value.starts_with(QUOTE) && value.ends_with(QUOTE);
    let raw: String = if quoted {
        value
            .chars()
            .skip(1)
            .take(value.chars().count().saturating_sub(2))
            .collect::<String>()
            .replace("\"\"", "\"")
    } else {
        value.to_owned()
    };
    if quoted
        && dialect.is_some_and(|name| CASE_SENSITIVE_DIALECTS.contains(&name))
        && !ignore_quoted_case
    {
        return raw;
    }
    if dialect == Some(SNOWFLAKE) {
        upper(&raw)
    } else {
        casefold(&raw)
    }
}

/// The first column of `columns` that `name` binds to, if any.
pub(crate) fn resolve_binding_column<'a>(
    name: &str,
    columns: &'a [(String, String)],
    dialect: Option<&str>,
    ignore_quoted_case: bool,
) -> Option<&'a str> {
    let dialect = binding_dialect(dialect);
    let expected = identity(name, dialect, ignore_quoted_case);
    columns
        .iter()
        .map(|(column, _)| column.as_str())
        .find(|column| identity(column, dialect, ignore_quoted_case) == expected)
}
