use crate::sql_macros::_helpers::parsing::definition::parsed_definition;
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::SqlMacroDefinition;

/// The SQL macro `name` defined by the file at `path`, or why it is not a valid SQL macro.
pub fn parse_sql_macro(
    name: &str,
    path: &str,
    source: &str,
) -> Result<SqlMacroDefinition, SqlMacroError> {
    parsed_definition(name, path, source)
}
