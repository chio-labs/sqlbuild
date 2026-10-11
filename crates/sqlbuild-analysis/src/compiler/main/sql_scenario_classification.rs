//! A SQL scenario classified natively, as the compile attachment reads it.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::_helpers;
use crate::compiler::models::SqlScenarioCtes;

/// The scenario's classified CTEs, or its error.
pub fn extract_scenario(
    sql: &str,
    file_label: &str,
    syntax: &LexicalSyntax,
) -> Result<SqlScenarioCtes, String> {
    _helpers::sql_tests::scenario_extraction::extract_scenario(sql, file_label, syntax)
}
