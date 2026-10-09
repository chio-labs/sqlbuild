use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::_helpers;

/// The scenario's classification or error as JSON.
///
/// # Errors
///
/// The JSON encoder's message.
pub fn extract_scenario_json(
    sql: &str,
    file_label: &str,
    syntax: &LexicalSyntax,
) -> Result<String, String> {
    _helpers::sql_tests::scenario_extraction::extract_scenario_json(sql, file_label, syntax)
}
