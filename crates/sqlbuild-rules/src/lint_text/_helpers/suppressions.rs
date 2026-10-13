//! Suppression directive parsing and matching.

use std::sync::LazyLock;

use regex::Regex;
use sqlbuild_core::text::main::python_isspace::python_isspace;

use crate::lint_text::_helpers::lines::LineSpan;
use crate::lint_text::_helpers::sites::compiled;
use crate::lint_text::constants::{
    FORBIDDEN_FIX_REASON, FORBIDDEN_MESSAGE, FORBIDDEN_REMEDIATION, INVALID_MESSAGE,
    INVALID_REMEDIATION, NATIVE_RULE_PREFIX, REASON_REQUIRED_FIX_REASON, SUPPRESSION_CODE,
    SUPPRESSION_PATTERN, SUPPRESSION_PREFIX, UNUSED_REMEDIATION,
};
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::{
    RetainedViolation, SuppressibleViolation, SuppressionDirective, SuppressionFinding,
};

static SUPPRESSION: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(SUPPRESSION_PATTERN));

/// Valid directives, and the one-based lines of invalid ones.
pub(crate) fn parse_directives(
    lines: &[LineSpan<'_>],
) -> Result<(Vec<SuppressionDirective>, Vec<usize>), LintTextError> {
    let pattern: &Regex = compiled(&SUPPRESSION)?;
    let mut directives: Vec<SuppressionDirective> = Vec::new();
    let mut invalid: Vec<usize> = Vec::new();
    for (index, line) in lines.iter().enumerate() {
        if !line.content.to_lowercase().contains(SUPPRESSION_PREFIX) {
            continue;
        }
        let Some(captures) = pattern.captures(line.content) else {
            invalid.push(index + 1);
            continue;
        };
        let mut target: usize = index + 1;
        while target < lines.len() && skippable(lines[target].content) {
            target += 1;
        }
        directives.push(SuppressionDirective {
            code: captures["code"].to_string(),
            line: index + 1,
            target: target + 1,
        });
    }
    Ok((directives, invalid))
}

/// Blank lines and comment lines between a directive and the line it suppresses.
fn skippable(line: &str) -> bool {
    let stripped: &str = line.trim_start_matches(python_isspace);
    stripped.is_empty() || stripped.starts_with("--")
}

/// Whether a retained violation is the native finding one directive suppresses.
pub(crate) fn matches_directive(
    item: &RetainedViolation,
    violations: &[SuppressibleViolation],
    file: usize,
    directive: &SuppressionDirective,
) -> bool {
    let (item_file, line, code, native): (usize, usize, &str, bool) = match item {
        RetainedViolation::Existing(index) => {
            let violation: &SuppressibleViolation = &violations[*index];
            (
                violation.file,
                violation.line,
                &violation.code,
                violation.native,
            )
        }
        RetainedViolation::Added(finding) => (finding.file, finding.line, SUPPRESSION_CODE, true),
    };
    item_file == file
        && line == directive.target
        && code == directive.code
        && native
        && code.starts_with(NATIVE_RULE_PREFIX)
}

/// Findings for every directive line when the project forbids suppressions.
pub(crate) fn forbidden_findings(
    file: usize,
    directives: &[SuppressionDirective],
    invalid: &[usize],
) -> Vec<RetainedViolation> {
    let mut lines: Vec<usize> = invalid
        .iter()
        .copied()
        .chain(directives.iter().map(|directive| directive.line))
        .collect();
    lines.sort_unstable();
    lines.dedup();
    lines
        .into_iter()
        .map(|line| {
            RetainedViolation::Added(SuppressionFinding {
                file,
                line,
                message: FORBIDDEN_MESSAGE.to_string(),
                remediation: FORBIDDEN_REMEDIATION,
                fault: true,
                fix: None,
                fix_unavailable_reason: Some(FORBIDDEN_FIX_REASON),
            })
        })
        .collect()
}

/// The finding for an invalid directive line.
pub(crate) fn invalid_finding(file: usize, line: usize) -> RetainedViolation {
    RetainedViolation::Added(SuppressionFinding {
        file,
        line,
        message: INVALID_MESSAGE.to_string(),
        remediation: INVALID_REMEDIATION,
        fault: false,
        fix: None,
        fix_unavailable_reason: Some(REASON_REQUIRED_FIX_REASON),
    })
}

/// The finding for a directive that suppressed nothing, with an edit removing its line.
pub(crate) fn unused_finding(
    file: usize,
    directive: &SuppressionDirective,
    span: &LineSpan<'_>,
) -> RetainedViolation {
    RetainedViolation::Added(SuppressionFinding {
        file,
        line: directive.line,
        message: format!("Unused suppression for {}", directive.code),
        remediation: UNUSED_REMEDIATION,
        fault: false,
        fix: Some((span.start, span.end)),
        fix_unavailable_reason: None,
    })
}
