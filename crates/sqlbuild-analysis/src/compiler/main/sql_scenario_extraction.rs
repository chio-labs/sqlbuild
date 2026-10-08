use crate::compiler::_helpers;

/// Python's extracted scenario CTEs as JSON, or `None` where Python must extract the scenario.
pub fn extract_scenario_json(sql: &str, file_label: &str) -> Result<Option<String>, String> {
    _helpers::sql_tests::scenario_extraction::extract_scenario_json(sql, file_label)
}
