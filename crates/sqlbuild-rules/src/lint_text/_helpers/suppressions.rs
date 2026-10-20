//! Inline suppression directives in SQL comments, rejected in favour of configured exceptions.

use std::sync::LazyLock;

use regex::Regex;

use crate::constants::SETTING_SNIPPET_INDENT;
use crate::lint_text::_helpers::lines::LineSpan;
use crate::lint_text::_helpers::sites::compiled;
use crate::lint_text::constants::{
    BLOCK_COMMENT_CLOSER, BLOCK_COMMENT_OPENER, COMMENT_OPENER_BYTES, CROSS_JOIN_CODE,
    CROSS_JOIN_RELATION_PATTERN, DIRECTIVE_FIX_REASON, DIRECTIVE_MARKER, DIRECTIVE_MESSAGE,
    DIRECTIVE_PATTERN, LINE_COMMENT_PREFIX, REASON_PLACEHOLDER, RULE_PLACEHOLDER,
};
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::SuppressionFinding;
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;
use sqlbuild_core::text::main::python_isspace::python_isspace;
use sqlbuild_sqltext::sql_scan::main::dialect_non_code_ranges::dialect_non_code_ranges;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

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

/// The rejection finding for every directive inside a SQL comment of one file.
pub(crate) fn directive_findings(
    file: usize,
    path: &str,
    (contents, lines): (&str, &[LineSpan<'_>]),
) -> Result<Vec<SuppressionFinding>, LintTextError> {
    if !mentions_directive(contents) {
        return Ok(Vec::new());
    }
    let pattern: &Regex = compiled(&DIRECTIVE)?;
    let relation_pattern: &Regex = compiled(&CROSS_JOIN_RELATION)?;
    let mut findings: Vec<SuppressionFinding> = Vec::new();
    for (start, end) in comment_ranges(contents) {
        let body: &str = comment_body(&contents[start..end]);
        let body_start: usize = start + COMMENT_OPENER_BYTES;
        for captures in pattern.captures_iter(body) {
            let Some(found) = captures.get(0) else {
                continue;
            };
            let Some(index) = line_index(contents, lines, body_start + found.start()) else {
                continue;
            };
            let text = |name: &str| -> Option<String> {
                captures
                    .name(name)
                    .map(|value| value.as_str().trim().to_owned())
                    .filter(|value| !value.is_empty())
            };
            let code: Option<String> = text("code");
            let relation: Option<String> = if code.as_deref() == Some(CROSS_JOIN_CODE) {
                target_line(contents, lines, (index, start))
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
    }
    Ok(findings)
}

/// A cheap check that `contents` may hold a directive at all.
fn mentions_directive(contents: &str) -> bool {
    contents
        .as_bytes()
        .windows(DIRECTIVE_MARKER.len())
        .any(|window| window.eq_ignore_ascii_case(DIRECTIVE_MARKER))
}

/// Byte ranges of the `--` line comments and `/* */` block comments, skipping quoted text.
fn comment_ranges(contents: &str) -> Vec<(usize, usize)> {
    let syntax = LexicalSyntax {
        line_comment_prefixes: vec![LINE_COMMENT_PREFIX.to_owned()],
        ..LexicalSyntax::default()
    };
    dialect_non_code_ranges(contents, &syntax)
        .into_iter()
        .filter(|(start, _)| {
            let rest: &str = &contents[*start..];
            rest.starts_with(LINE_COMMENT_PREFIX) || rest.starts_with(BLOCK_COMMENT_OPENER)
        })
        .collect()
}

/// A comment's text without its opener and, for a block comment, its closer.
fn comment_body(comment: &str) -> &str {
    let body: &str = &comment[COMMENT_OPENER_BYTES..];
    if comment.starts_with(BLOCK_COMMENT_OPENER) {
        body.strip_suffix(BLOCK_COMMENT_CLOSER).unwrap_or(body)
    } else {
        body
    }
}

/// The zero-based line holding byte `offset` of `contents`.
fn line_index(contents: &str, lines: &[LineSpan<'_>], offset: usize) -> Option<usize> {
    let position: usize = contents[..offset].chars().count();
    lines
        .iter()
        .position(|line| line.start <= position && position < line.end)
}

/// The code a directive covers: code before its comment, else the next non-comment line.
fn target_line<'a>(
    contents: &'a str,
    lines: &[LineSpan<'a>],
    (directive, comment_start): (usize, usize),
) -> Option<&'a str> {
    let line: &LineSpan<'a> = lines.get(directive)?;
    let line_start: usize = contents
        .char_indices()
        .nth(line.start)
        .map_or(contents.len(), |(byte, _)| byte);
    let before: &str = contents.get(line_start..comment_start).unwrap_or_default();
    if !before.trim_matches(python_isspace).is_empty() {
        return Some(before);
    }
    lines
        .iter()
        .skip(directive + 1)
        .map(|line| line.content)
        .find(|content| {
            let stripped: &str = content.trim_start_matches(python_isspace);
            !stripped.is_empty() && !stripped.starts_with(LINE_COMMENT_PREFIX)
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
