//! The scalar arguments of a type as Polyglot parses it.

use polyglot_sql::{DataType, Dialect, DialectType};
use serde_json::{Map, Value};

use crate::type_system::_helpers::parsed::parse_type;
use crate::type_system::_helpers::shallow_args::shallow_args;

/// `parse_data_type(type_sql, dialect=...).args` scalars, or the parse error text.
pub fn polyglot_type_args(type_sql: &str, dialect: &str) -> Result<Map<String, Value>, String> {
    let polyglot: Dialect = dialect
        .parse::<DialectType>()
        .map(Dialect::get)
        .map_err(|_| format!("unknown dialect '{dialect}'"))?;
    let parsed: DataType = parse_type(type_sql, &polyglot)?;
    Ok(shallow_args(&parsed))
}
