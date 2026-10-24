//! A SQL macro's declared `returns` type checked against the adapter's SQL analysis dialect.

use polyglot_sql::DialectType;

use crate::sql_macros::_helpers::typing::returns_check::adapter_dialect;

/// Why `returns` is not a type the adapter's SQL analysis dialect parses.
pub(crate) fn returns_type_error(returns: &str, adapter: &str, context: &str) -> Option<String> {
    let dialect_name: &str = adapter_dialect(adapter);
    let Ok(dialect) = dialect_name.parse::<DialectType>() else {
        return None;
    };
    let Err(error) = polyglot_sql::parse_data_type(returns, dialect) else {
        return None;
    };
    let reason: String = error.to_string();
    Some(format!(
        "{context} type '{returns}' is not valid for adapter '{adapter}' SQL analysis dialect \
         '{dialect_name}': {reason}"
    ))
}
