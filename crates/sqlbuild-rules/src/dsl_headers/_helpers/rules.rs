//! The header rules of one header: parseable values, a short present description, no trailing spaces.

use sqlbuild_sqltext::header_strings::main::prose_string::prose_string;

use crate::dsl_headers::_helpers::prose_layout::{description_string_span, prose_length};
use crate::dsl_headers::_helpers::quoted::split_outside_quotes;
use crate::dsl_headers::_helpers::text::{
    chars, line_count, position, rstrip, slice, string, strip,
};
use crate::dsl_headers::constants::{
    DESCRIPTION_HEADER_KINDS, DESCRIPTION_REQUIRED_HEADER_KINDS, RULE_DESCRIPTION_LENGTH,
    RULE_DESCRIPTION_PRESENT, RULE_HEADER_PARSE, RULE_HEADER_WHITESPACE, SQL_MACRO_HEADER_KIND,
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

fn parse_fault(
    (text, starts): (&[char], &[usize]),
    header: &HeaderSpan,
    failure: ParseFailure,
) -> HeaderViolation {
    let kind: &str = &header.kind;
    let open: Option<usize> = slice(text, header.start, header.end)
        .iter()
        .position(|character| *character == '(');
    let offset: usize = match (failure.position, open) {
        (Some(position), Some(open)) => header.start + open + 1 + position,
        _ => header.start,
    };
    violation_at(
        starts,
        offset,
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
    if kind == SQL_MACRO_HEADER_KIND {
        return Ok(Vec::new());
    }
    let values: P::Values = match parser.parse(kind, &string(inner_header_text(header_text))) {
        ParseOutcome::Parsed(values) => values,
        ParseOutcome::Rejected(failure) | ParseOutcome::Raised(_, failure) => {
            return Ok(vec![parse_fault((text, starts), header, failure)]);
        }
    };
    let mut violations: Vec<HeaderViolation> = Vec::new();
    let described: bool = DESCRIPTION_HEADER_KINDS.contains(&kind);
    let span: Option<(usize, usize)> = described
        .then(|| description_string_span(header_text))
        .flatten();
    let authored: Option<String> = span.and_then(|(start, _)| authored_prose(header_text, start));
    let description: Option<String> = match parser.description(&values)? {
        Some(_) if authored.is_some() => authored,
        description => description,
    };
    if DESCRIPTION_REQUIRED_HEADER_KINDS.contains(&kind)
        && description
            .as_deref()
            .is_none_or(|description| strip(&chars(description)).is_empty())
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
        let lines: usize = match span {
            Some(span) => prose_length(&description, header_text, span, config.line_width),
            None => line_count(&chars(&description)),
        };
        let limit: usize = config.max_description_lines;
        if lines > limit {
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

/// The folded text of the prose string at `start`, if it reads.
fn authored_prose(header_text: &[char], start: usize) -> Option<String> {
    let Ok(prose) = prose_string(header_text, start) else {
        return None;
    };
    Some(prose.value)
}
