//! Public compiler entry point for native references in one rendered model's SQL.

use crate::compiler::_helpers::model_rendering::batch::sql_references;
use crate::compiler::_helpers::model_rendering::syntax::parse_lexical_syntax;
use crate::compiler::_helpers::sql_references::extraction::StaticReference;

pub(crate) fn model_sql_references(
    sql: &str,
    syntax_json: &str,
) -> Result<Option<Vec<StaticReference>>, String> {
    Ok(sql_references(sql, &parse_lexical_syntax(syntax_json)?))
}
