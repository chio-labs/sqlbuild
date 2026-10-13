//! `format_result`: one rules result for the requested CLI surface.

use crate::rule_results::_helpers::rendering::{result_json, result_text};
use crate::rule_results::models::{ResultCounts, RuleFinding};

/// The result as indented JSON, or as the text report.
pub fn format_result(findings: &[RuleFinding], counts: ResultCounts, json_output: bool) -> String {
    if json_output {
        return result_json(findings, counts);
    }
    result_text(findings, counts)
}
