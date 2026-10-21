//! `reject_inline_suppressions`: an error for every `sqb: ignore` directive in a SQL comment.

use rayon::iter::{IndexedParallelIterator, IntoParallelRefIterator, ParallelIterator};

use crate::lint_text::_helpers::lines::{LineSpan, line_spans};
use crate::lint_text::_helpers::suppressions::directive_findings;
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::SuppressionFinding;

/// A finding per directive line of each `(relative path, contents)`, printing its exception entry.
pub fn reject_inline_suppressions(
    files: &[(&str, &str)],
) -> Result<Vec<SuppressionFinding>, LintTextError> {
    let per_file: Vec<Result<Vec<SuppressionFinding>, LintTextError>> = files
        .par_iter()
        .enumerate()
        .map(|(file, (path, contents))| {
            let lines: Vec<LineSpan<'_>> = line_spans(contents);
            directive_findings(file, path, (contents, &lines))
        })
        .collect();
    let mut findings: Vec<SuppressionFinding> = Vec::new();
    for file_findings in per_file {
        findings.extend(file_findings?);
    }
    Ok(findings)
}
