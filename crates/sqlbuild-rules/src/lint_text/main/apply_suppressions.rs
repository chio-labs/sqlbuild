//! `apply_suppressions`: reason-required next-line suppressions applied to lint violations.

use crate::lint_text::_helpers::lines::{LineSpan, line_spans};
use crate::lint_text::_helpers::suppressions::{
    forbidden_findings, invalid_finding, matches_directive, parse_directives, unused_finding,
};
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::{RetainedViolation, SuppressibleViolation};

/// Remove matching next-line diagnostics, or reject every directive when suppressions are off.
pub fn apply_suppressions(
    files: &[&str],
    violations: &[SuppressibleViolation],
    allow_suppressions: bool,
) -> Result<Vec<RetainedViolation>, LintTextError> {
    let mut retained: Vec<RetainedViolation> = (0..violations.len())
        .map(RetainedViolation::Existing)
        .collect();
    for (file, contents) in files.iter().enumerate() {
        let lines: Vec<LineSpan<'_>> = line_spans(contents);
        let (directives, invalid) = parse_directives(&lines)?;
        if !allow_suppressions {
            retained.extend(forbidden_findings(file, &directives, &invalid));
            continue;
        }
        retained.extend(invalid.into_iter().map(|line| invalid_finding(file, line)));
        for directive in directives {
            match retained
                .iter()
                .position(|item| matches_directive(item, violations, file, &directive))
            {
                Some(index) => {
                    let _ = retained.remove(index);
                }
                None => retained.push(unused_finding(file, &directive, &lines[directive.line - 1])),
            }
        }
    }
    Ok(retained)
}
