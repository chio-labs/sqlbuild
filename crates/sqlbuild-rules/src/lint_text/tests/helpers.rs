use crate::lint_text::constants::{DIRECTIVE_FIX_REASON, DIRECTIVE_MESSAGE};
use crate::lint_text::models::SuppressionFinding;

const INDENT: &str = "\n            ";

/// The rejection finding for a directive on `line`, printing `rest` after the entry header.
pub(crate) fn directive_finding(line: usize, rule: &str, rest: &[&str]) -> SuppressionFinding {
    let mut remediation: String = format!(
        "Remove this comment, then fix the {rule} finding, or record it as a reviewed exception \
         in sqlbuild_project.toml:{INDENT}[[rules.rule_exceptions]]"
    );
    for line in rest {
        remediation.push_str(INDENT);
        remediation.push_str(line);
    }
    SuppressionFinding {
        file: 0,
        line,
        message: DIRECTIVE_MESSAGE.to_owned(),
        remediation,
        fault: true,
        fix: None,
        fix_unavailable_reason: Some(DIRECTIVE_FIX_REASON),
    }
}
