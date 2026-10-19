//! Inline suppression directives, which SQLBuild rejects in favour of configured exceptions.

use std::sync::LazyLock;

use regex::Regex;

use crate::constants::SETTING_SNIPPET_INDENT;
use crate::lint_text::_helpers::lines::LineSpan;
use crate::lint_text::_helpers::sites::compiled;
use crate::lint_text::constants::{
    CROSS_JOIN_CODE, CROSS_JOIN_RELATION_PATTERN, DIRECTIVE_FIX_REASON, DIRECTIVE_MESSAGE,
    DIRECTIVE_PATTERN, REASON_PLACEHOLDER, RULE_PLACEHOLDER, SUPPRESSION_PREFIX,
};
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::SuppressionFinding;
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;
use sqlbuild_core::text::main::python_isspace::python_isspace;

static DIRECTIVE: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(DIRECTIVE_PATTERN));
static CROSS_JOIN_RELATION: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(CROSS_JOIN_RELATION_PATTERN));

/// One inline directive: what it names, and what the exception entry for it holds.
struct Directive {
    line: usize,
    code: Option<String>,
    reason: Option<String>,
    relation: Option<String>,
}

/// The rejection finding for every directive line in one file.
pub(crate) fn directive_findings(
    file: usize,
    path: &str,
    lines: &[LineSpan<'_>],
) -> Result<Vec<SuppressionFinding>, LintTextError> {
    let pattern: &Regex = compiled(&DIRECTIVE)?;
    let relation_pattern: &Regex = compiled(&CROSS_JOIN_RELATION)?;
    let mut findings: Vec<SuppressionFinding> = Vec::new();
    for (index, line) in lines.iter().enumerate() {
        if !line.content.to_lowercase().contains(SUPPRESSION_PREFIX) {
            continue;
        }
        let captures = pattern.captures(line.content);
        let text = |name: &str| -> Option<String> {
            captures
                .as_ref()
                .and_then(|found| found.name(name))
                .map(|found| found.as_str().trim().to_owned())
                .filter(|value| !value.is_empty())
        };
        let code: Option<String> = text("code");
        let relation: Option<String> = if code.as_deref() == Some(CROSS_JOIN_CODE) {
            target_line(lines, index)
                .and_then(|target| cross_joined_relation(relation_pattern, target))
        } else {
            None
        };
        let directive = Directive {
            line: index + 1,
            code,
            reason: text("reason"),
            relation,
        };
        findings.push(SuppressionFinding {
            file,
            line: directive.line,
            message: DIRECTIVE_MESSAGE.to_owned(),
            remediation: remediation(&directive, path),
            fault: true,
            fix: None,
            fix_unavailable_reason: Some(DIRECTIVE_FIX_REASON),
        });
    }
    Ok(findings)
}

/// The next line that is neither blank nor a comment: the line a directive meant to cover.
fn target_line<'a>(lines: &[LineSpan<'a>], directive: usize) -> Option<&'a str> {
    lines
        .iter()
        .skip(directive + 1)
        .map(|line| line.content)
        .find(|content| {
            let stripped: &str = content.trim_start_matches(python_isspace);
            !stripped.is_empty() && !stripped.starts_with("--")
        })
}

/// The relation a `CROSS JOIN` on `line` reads: a dependency's name or an authored identifier.
fn cross_joined_relation(pattern: &Regex, line: &str) -> Option<String> {
    let captures = pattern.captures(line)?;
    captures
        .name("dependency")
        .or_else(|| captures.name("identifier"))
        .map(|found| found.as_str().to_owned())
}

/// Remove-and-declare help, with the exact `[[rules.rule_exceptions]]` entry to add.
fn remediation(directive: &Directive, path: &str) -> String {
    let mut entry: Vec<String> = vec![
        "[[rules.rule_exceptions]]".to_owned(),
        format!(
            "rule = {}",
            toml_string(directive.code.as_deref().unwrap_or(RULE_PLACEHOLDER))
        ),
        format!("path = {}", toml_string(path)),
    ];
    if let Some(relation) = &directive.relation {
        entry.push(format!("relation = {}", toml_string(relation)));
    }
    entry.push(format!(
        "reason = {}",
        toml_string(directive.reason.as_deref().unwrap_or(REASON_PLACEHOLDER))
    ));
    let rule: &str = directive.code.as_deref().unwrap_or("Rule");
    let snippet: String = entry
        .iter()
        .map(|line| format!("\n{SETTING_SNIPPET_INDENT}{line}"))
        .collect();
    format!(
        "Remove this comment, then fix the {rule} finding, or record it as a reviewed exception in \
         {PROJECT_CONFIG_FILENAME}:{snippet}"
    )
}

fn toml_string(value: &str) -> String {
    toml::Value::String(value.to_owned()).to_string()
}
