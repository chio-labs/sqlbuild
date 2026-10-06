use polyglot_sql::DialectType;

/// Every catalogued or parser-typed built-in function name of `dialect`, lower-cased.
pub fn builtin_function_names(dialect: DialectType) -> Vec<String> {
    crate::sql_tokens::_helpers::builtin_functions::builtin_function_names(dialect)
}
