//! `reject_inline_suppressions`: an error for every inline `-- sqb: ignore` directive.

use crate::lint_text::_helpers::lines::{LineSpan, line_spans};
use crate::lint_text::_helpers::suppressions::directive_findings;
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::SuppressionFinding;

/// A finding per directive line of each `(relative path, contents)`, printing its exception entry.
pub fn reject_inline_suppressions(
    files: &[(&str, &str)],
) -> Result<Vec<SuppressionFinding>, LintTextError> {
    let mut findings: Vec<SuppressionFinding> = Vec::new();
    for (file, (path, contents)) in files.iter().enumerate() {
        let lines: Vec<LineSpan<'_>> = line_spans(contents);
        findings.extend(directive_findings(file, path, &lines)?);
    }
    Ok(findings)
}
