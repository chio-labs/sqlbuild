//! The expectation rows and failure details under a scenario result.

use crate::cli_text::models::CliStyle;
use crate::scenario_command::_helpers::rows::{result_error, rows_label};
use crate::scenario_command::constants::{
    EXPECTATION_ERROR_INDENT, EXPECTATION_LABEL_WIDTH, EXPECTATION_NAME_WIDTH, FAIL_STATUS,
    PASS_STATUS,
};
use crate::scenario_command::models::{CodedText, ScenarioResultRow};

/// One `expect` row.
fn expectation_line(item: &str, (failed, detail): (bool, String), style: CliStyle) -> String {
    let status: String = style.status(if failed { FAIL_STATUS } else { PASS_STATUS });
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
        let detail: String = if expected.failed {
            format!("  {} mismatched", expected.mismatched_row_count)
        } else {
            String::new()
        };
        text.push_str(&expectation_line(
            &format!("expected {}", expected.model_name),
            (expected.failed, detail),
            style,
        ));
        text.push_str(&expectation_error(expected.error.as_ref(), style));
    }
    for assertion in &row.assertions {
        let detail: String = if assertion.failed {
            format!(
                "  {} {}",
                assertion.failing_row_count,
                rows_label(assertion.failing_row_count)
            )
        } else {
            String::new()
        };
        text.push_str(&expectation_line(
            &format!("assertion {}", assertion.name),
            (assertion.failed, detail),
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
        text.push_str(&format!(
            "    expected {}: actual={} expected={} mismatched={}\n",
            expected.model_name,
            expected.actual_row_count,
            expected.expected_row_count,
            expected.mismatched_row_count
        ));
    }
    for assertion in row.assertions.iter().filter(|assertion| assertion.failed) {
        text.push_str(&format!(
            "    assertion {}: failing_rows={}\n",
            assertion.name, assertion.failing_row_count
        ));
        if let Some(sample) = &assertion.first_sample {
            text.push_str(&format!("    sample: {sample}\n"));
        }
    }
    text
}
