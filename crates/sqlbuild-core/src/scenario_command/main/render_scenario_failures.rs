//! The closing list of failed scenarios, so failures stay visible after long output.

use crate::cli_text::models::CliStyle;
use crate::scenario_command::_helpers::rows::result_error;
use crate::scenario_command::constants::{ERROR_STATUS, FAIL_STATUS};
use crate::scenario_command::models::ScenarioResultRow;
use crate::text::main::python_splitlines::python_splitlines;

/// The first line of a failed scenario's error, or of its first failed expectation.
fn first_failure_line(row: &ScenarioResultRow, style: CliStyle) -> String {
    let first_line = |text: String| -> String {
        python_splitlines(&text)
            .into_iter()
            .next()
            .unwrap_or_default()
            .to_owned()
    };
    if let Some(error) = row.error.as_ref().filter(|error| !error.message.is_empty()) {
        return first_line(result_error(error, style));
    }
    if let Some(expected) = row.expected.iter().find(|expected| expected.failed) {
        return match (&expected.error, expected.mismatched_row_count) {
            (Some(error), _) => first_line(result_error(error, style)),
            (None, Some(mismatched)) => format!(
                "expected {}: {mismatched} mismatched, {} missing",
                expected.model_name,
                expected.missing_row_count.unwrap_or_default()
            ),
            (None, None) => format!("expected {} did not run", expected.model_name),
        };
    }
    if let Some(assertion) = row.assertions.iter().find(|assertion| assertion.failed) {
        return match (&assertion.error, assertion.failing_row_count) {
            (Some(error), _) => first_line(result_error(error, style)),
            (None, Some(count)) => format!("assertion {}: {count} failing rows", assertion.name),
            (None, None) => format!("assertion {} did not run", assertion.name),
        };
    }
    String::new()
}

/// `Failures:` with each failed scenario and its first error line, or nothing when all passed.
#[must_use]
pub fn render_scenario_failures(rows: &[ScenarioResultRow], style: CliStyle) -> String {
    let failed: Vec<&ScenarioResultRow> = rows
        .iter()
        .filter(|row| row.status == FAIL_STATUS || row.status == ERROR_STATUS)
        .collect();
    if failed.is_empty() {
        return String::new();
    }
    let mut text: String = String::from("\nFailures:\n\n");
    for row in failed {
        text.push_str(&format!("  {}\n", row.name));
        let line: String = first_failure_line(row, style);
        if !line.is_empty() {
            text.push_str(&format!("    {line}\n"));
        }
    }
    text
}
