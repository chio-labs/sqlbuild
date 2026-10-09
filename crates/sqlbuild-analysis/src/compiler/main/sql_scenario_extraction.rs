use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::_helpers;

/// Python's scenario extraction outcome as JSON, or `None` where Python must extract the scenario.
pub fn extract_scenario_json(
    sql: &str,
    file_label: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<String>, String> {
    _helpers::sql_tests::scenario_extraction::extract_scenario_json(sql, file_label, syntax)
}
