//! The header rules of one header: parseable values, a short present description, no trailing spaces.

use crate::dsl_headers::_helpers::quoted::{
    decode_description, description_value_span, split_outside_quotes,
};
use crate::dsl_headers::_helpers::text::{line_count, position, rstrip, slice, string, strip};
use crate::dsl_headers::_helpers::wrap::wrap_header_description;
use crate::dsl_headers::constants::{
    DESCRIPTION_HEADER_KINDS, DESCRIPTION_REQUIRED_HEADER_KINDS, RULE_DESCRIPTION_LENGTH,
    RULE_DESCRIPTION_PRESENT, RULE_HEADER_PARSE, RULE_HEADER_WHITESPACE,
};
use crate::dsl_headers::main::inner_header_text::inner_header_text;
use crate::dsl_headers::models::{
    HeaderRulesConfig, HeaderSeverity, HeaderSpan, HeaderViolation, ParseFailure, ParseOutcome,
};
use crate::dsl_headers::types::HeaderParser;

/// One violation reported at the start of `header`.
pub(crate) fn violation_at(
    starts: &[usize],
    offset: usize,
    (code, severity): (&'static str, HeaderSeverity),
    (message, remediation): (String, String),
) -> HeaderViolation {
    let (line, column) = position(offset, starts);
    HeaderViolation {
        line,
        column,
        code,
        message,
        severity,
        remediation,
    }
}

fn parse_fault(starts: &[usize], header: &HeaderSpan, failure: ParseFailure) -> HeaderViolation {
    let kind: &str = &header.kind;
    violation_at(
        starts,
        header.start,
        (RULE_HEADER_PARSE, HeaderSeverity::Fault),
        (
            format!("{kind}() header could not be parsed: {}", failure.message),
            failure
                .help
                .unwrap_or_else(|| format!("Correct the {kind}() header syntax.")),
        ),
    )
}

pub(crate) fn value_violations<P: HeaderParser>(
    (text, starts): (&[char], &[usize]),
    header: &HeaderSpan,
    config: HeaderRulesConfig,
    parser: &P,
) -> Result<Vec<HeaderViolation>, P::Error> {
    let header_text: &[char] = slice(text, header.start, header.end);
    let kind: &str = &header.kind;
    let values: P::Values = match parser.parse(kind, &string(inner_header_text(header_text))) {
        ParseOutcome::Parsed(values) => values,
        ParseOutcome::Rejected(failure) | ParseOutcome::Raised(_, failure) => {
            return Ok(vec![parse_fault(starts, header, failure)]);
        }
    };
    let mut violations: Vec<HeaderViolation> = Vec::new();
    let described: bool = DESCRIPTION_HEADER_KINDS.contains(&kind);
    let span: Option<(usize, usize)> = described
        .then(|| description_value_span(header_text))
        .flatten();
    let description: Option<Vec<char>> = match (parser.description(&values)?, span) {
        (Some(_), Some((start, end))) => Some(decode_description(
            slice(header_text, start, end),
            header_text[start - 1],
        )),
        (description, _) => description.map(|description| description.chars().collect()),
    };
    if DESCRIPTION_REQUIRED_HEADER_KINDS.contains(&kind)
        && description
            .as_deref()
            .is_none_or(|description| strip(description).is_empty())
    {
        violations.push(violation_at(
            starts,
            header.start,
            (RULE_DESCRIPTION_PRESENT, HeaderSeverity::Fault),
            (
                format!("{kind}() header requires a description"),
                format!(
                    "Add description \"<what it is>\" to the {kind}() header; \
                     every named resource must be described."
                ),
            ),
        ));
    }
    if described && let Some(description) = description {
        let formatted: Vec<char> = match span {
            Some(span) => {
                wrap_header_description(&description, header_text, span, config.line_width)
            }
            None => description,
        };
        let limit: usize = config.max_description_lines;
        if line_count(&formatted) > limit {
            violations.push(violation_at(
                starts,
                header.start,
                (RULE_DESCRIPTION_LENGTH, HeaderSeverity::Fault),
                (
                    format!("Description exceeds {limit} lines"),
                    format!("Shorten the description to {limit} lines."),
                ),
            ));
        }
    }
    Ok(violations)
}

pub(crate) fn whitespace_violation(
    (text, starts): (&[char], &[usize]),
    header: &HeaderSpan,
) -> Option<HeaderViolation> {
    let header_text: &[char] = slice(text, header.start, header.end);
    split_outside_quotes(header_text)
        .iter()
        .any(|line| rstrip(line).len() != line.len())
        .then(|| {
            violation_at(
                starts,
                header.start,
                (RULE_HEADER_WHITESPACE, HeaderSeverity::Warning),
                (
                    format!("{}() header contains trailing whitespace", header.kind),
                    "Run sqb format to remove trailing header whitespace.".to_owned(),
                ),
            )
        })
}
