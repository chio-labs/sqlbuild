//! The pre-execution error for a scenario expected CTE whose columns do not fit its model.

use crate::compiler::models::ScenarioExpectedColumns;

/// Why the expected CTE cannot be compared with its model, or `None` when it can.
#[must_use]
pub fn scenario_expected_column_message(
    scenario_name: &str,
    model_name: &str,
    columns: &ScenarioExpectedColumns,
    all_columns: bool,
) -> Option<String> {
    let mut problems: Vec<String> = Vec::new();
    if all_columns && !columns.unlisted.is_empty() {
        problems.push(format!(
            "does not list columns that model '{model_name}' outputs: {}",
            columns.unlisted.join(", ")
        ));
    }
    if !columns.unknown.is_empty() {
        problems.push(format!(
            "lists columns that model '{model_name}' does not output: {}",
            columns.unknown.join(", ")
        ));
    }
    if problems.is_empty() {
        return None;
    }
    Some(format!(
        "scenario '{scenario_name}' expected output __expected__{model_name} {}",
        problems.join("; and ")
    ))
}
