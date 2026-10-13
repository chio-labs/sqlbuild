//! A format run as stable machine-readable JSON.

use crate::format_command::_helpers::json_objects::{count, finding_object, fix_object, text};
use crate::format_command::models::LintReport;
use crate::json::errors::JsonEmitError;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// The report with sorted keys and compact separators, followed by a newline.
pub fn render_lint_json(report: &LintReport) -> Result<String, JsonEmitError> {
    let document: JsonValue = JsonValue::Object(vec![
        ("faults".to_owned(), count(report.fault_count())),
        ("files_checked".to_owned(), count(report.files_checked)),
        (
            "formatted_files".to_owned(),
            JsonValue::Array(
                report
                    .formatted_files
                    .iter()
                    .map(|path| text(path))
                    .collect(),
            ),
        ),
        (
            "rule_fixes".to_owned(),
            JsonValue::Array(report.rule_fixes.iter().map(fix_object).collect()),
        ),
        (
            "violations".to_owned(),
            JsonValue::Array(report.findings.iter().map(finding_object).collect()),
        ),
        ("warnings".to_owned(), count(report.warning_count())),
    ]);
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    Ok(format!(
        "{}\n",
        dumps(&document, &JsonDialect::Stdlib(options))?
    ))
}
