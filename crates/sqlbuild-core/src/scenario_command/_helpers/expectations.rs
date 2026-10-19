//! The expectation rows and failure details under a scenario result.

use crate::cli_text::models::CliStyle;
use crate::scenario_command::_helpers::rows::{result_error, rows_label};
use crate::scenario_command::constants::{
    ERROR_STATUS, EXPECTATION_ERROR_INDENT, EXPECTATION_LABEL_WIDTH, EXPECTATION_NAME_WIDTH,
    FAIL_STATUS, PASS_STATUS,
};
use crate::scenario_command::models::{CodedText, ScenarioResultRow};

/// One `expect` row under `status`.
fn expectation_line(item: &str, (status, detail): (&str, String), style: CliStyle) -> String {
    let status: String = style.status(status);
    format!(
        "    {:<EXPECTATION_LABEL_WIDTH$}{item:<EXPECTATION_NAME_WIDTH$} {status}{detail}\n",
        "expect"
    )
}

/// The coded error under an expectation row, when it has one.
fn expectation_error(error: Option<&CodedText>, style: CliStyle) -> String {
    error.map_or_else(String::new, |error| {
        format!(
            "{:>EXPECTATION_ERROR_INDENT$}{}\n",
            "",
            result_error(error, style)
        )
    })
}

/// Each expected comparison and assertion row, with its error.
pub(crate) fn expectation_rows(row: &ScenarioResultRow, style: CliStyle) -> String {
    let mut text: String = String::new();
    for expected in &row.expected {
        let (status, detail): (&str, String) =
            match (expected.failed, expected.mismatched_row_count) {
                (false, _) => (PASS_STATUS, String::new()),
                (true, Some(mismatched)) => (
                    FAIL_STATUS,
                    format!(
                        "  {mismatched} mismatched, {} missing",
                        expected.missing_row_count.unwrap_or_default()
                    ),
                ),
                (true, None) => (ERROR_STATUS, String::new()),
            };
        text.push_str(&expectation_line(
            &format!("expected {}", expected.model_name),
            (status, detail),
            style,
        ));
        text.push_str(&expectation_error(expected.error.as_ref(), style));
    }
    for assertion in &row.assertions {
        let (status, detail): (&str, String) = match (assertion.failed, assertion.failing_row_count)
        {
            (false, _) => (PASS_STATUS, String::new()),
            (true, Some(count)) => (FAIL_STATUS, format!("  {count} {}", rows_label(count))),
            (true, None) => (ERROR_STATUS, String::new()),
        };
        text.push_str(&expectation_line(
            &format!("assertion {}", assertion.name),
            (status, detail),
            style,
        ));
        text.push_str(&expectation_error(assertion.error.as_ref(), style));
    }
    text
}

/// The counts of each failed expectation, and the first failing assertion sample.
pub(crate) fn expectation_failures(row: &ScenarioResultRow) -> String {
    let mut text: String = String::new();
    for expected in row.expected.iter().filter(|expected| expected.failed) {
        let (Some(actual), Some(expected_count), Some(mismatched)) = (
            expected.actual_row_count,
            expected.expected_row_count,
            expected.mismatched_row_count,
        ) else {
            continue;
        };
        text.push_str(&format!(
            "    expected {}: actual={actual} expected={expected_count} mismatched={mismatched} \
             missing={}\n",
            expected.model_name,
            expected.missing_row_count.unwrap_or_default()
        ));
    }
    for assertion in row.assertions.iter().filter(|assertion| assertion.failed) {
        let Some(failing) = assertion.failing_row_count else {
            continue;
        };
        text.push_str(&format!(
            "    assertion {}: failing_rows={failing}\n",
            assertion.name
        ));
        if let Some(sample) = &assertion.first_sample {
            text.push_str(&format!("    sample: {sample}\n"));
        }
    }
    text
}
