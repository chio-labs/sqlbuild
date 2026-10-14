//! A format run's human report.

use crate::cli_text::models::CliStyle;
use crate::format_command::_helpers::diagnostics::violation_block;
use crate::format_command::models::LintReport;

/// Changed files under `heading`, diagnostics, Rule fixes and the styled summary line.
#[must_use]
pub fn render_lint_text(report: &LintReport, style: CliStyle, heading: &str) -> String {
    let mut output: String = String::new();
    if !report.formatted_files.is_empty() {
        output.push_str(heading);
        output.push('\n');
        for path in &report.formatted_files {
            output.push_str(&format!("  {path}\n"));
        }
        output.push('\n');
    }
    if !report.findings.is_empty() {
        let blocks: Vec<String> = report
            .findings
            .iter()
            .map(|finding| violation_block(finding, style))
            .collect();
        output.push_str(&blocks.join("\n\n"));
        output.push_str("\n\n");
    }
    for fix in &report.rule_fixes {
        output.push_str(&format!(
            "{}  {}  {}:{}: {}\n",
            fix.status.to_uppercase(),
            fix.code,
            fix.file,
            fix.line,
            fix.reason
        ));
    }
    let faults: usize = report.fault_count();
    let warnings: usize = report.warning_count();
    let summary: String = format!(
        "Completed.  FAULT={faults}  WARN={warnings}  FILES={}",
        report.files_checked
    );
    let styled: String = if faults > 0 {
        style.error_strong(&summary)
    } else if warnings > 0 {
        style.warning_strong(&summary)
    } else {
        style.success_strong(&summary)
    };
    output.push_str(&styled);
    output.push('\n');
    output
}
