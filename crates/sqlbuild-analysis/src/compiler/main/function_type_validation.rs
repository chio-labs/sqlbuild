//! Function argument and return types checked against the adapter's SQL analysis dialect.

use crate::compiler::_helpers;

/// The error for a type the adapter's dialect cannot parse, or `Err` for a broken parse guard.
pub fn function_type_error(
    type_sql: &str,
    adapter_name: &str,
    context: &str,
) -> Result<Option<String>, String> {
    _helpers::polyglot::function_types::function_type_error(type_sql, adapter_name, context)
}
