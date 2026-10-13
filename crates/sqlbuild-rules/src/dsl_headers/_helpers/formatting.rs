//! Header formatting fixes: trailing spaces, leading comments, description and audit wrapping.

use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::dsl_headers::_helpers::audits::wrap_header;
use crate::dsl_headers::_helpers::quoted::{
    decode_description, description_value_span, escape_quoted, split_outside_quotes,
};
use crate::dsl_headers::_helpers::rules::violation_at;
use crate::dsl_headers::_helpers::text::{
    chars, line_count, line_starts, lstrip, rstrip, slice, string, tail,
};
use crate::dsl_headers::_helpers::wrap::{wrap_description, wrap_header_description};
use crate::dsl_headers::constants::{
    DESCRIPTION_HEADER_KINDS, DESCRIPTION_KEY, HEADER_INDENT, MODEL_KIND,
    RULE_LEADING_COMMENT_DESCRIPTION,
};
use crate::dsl_headers::main::inner_header_text::inner_header_text;
use crate::dsl_headers::main::scan_headers::scan_headers;
use crate::dsl_headers::models::{
    HeaderRulesConfig, HeaderSeverity, HeaderSpan, HeaderViolation, ParseOutcome,
};
use crate::dsl_headers::types::HeaderParser;

pub(crate) fn without_trailing_whitespace(text: &[char], headers: &[HeaderSpan]) -> Vec<char> {
    let mut updated: Vec<char> = Vec::with_capacity(text.len());
    let mut cursor: usize = 0;
    for header in headers {
        updated.extend(slice(text, cursor, header.start));
        let lines: Vec<&[char]> = split_outside_quotes(slice(text, header.start, header.end))
            .into_iter()
            .map(rstrip)
            .collect();
        updated.extend(lines.join(&'\n'));
        cursor = header.end;
    }
    updated.extend(tail(text, cursor));
    updated
}

/// The prose of the comment block before the first header, if it is only comments.
fn leading_comment(preamble: &[char]) -> Option<String> {
    let preamble: String = string(preamble);
    let stripped: &str = python_strip(&preamble);
    if stripped.is_empty() {
        return None;
    }
    if let Some(body) = stripped.strip_prefix("/*") {
        return body.find("*/").map(|end| body[..end].to_owned());
    }
    let mut lines: Vec<String> = Vec::new();
    for raw_line in python_splitlines(&preamble) {
        let candidate: &str = python_strip(raw_line);
        if let Some(comment) = candidate.strip_prefix("--") {
            lines.push(string(lstrip(&chars(comment))));
            continue;
        }
        if !lines.is_empty() {
            break;
        }
        if !candidate.is_empty() {
            return None;
        }
    }
    (!lines.is_empty()).then(|| lines.join("\n"))
}

/// The comment wrapped as a description, and the fault when it is too long.
fn relocated_description(
    comment: &str,
    config: HeaderRulesConfig,
    (text, header_start): (&[char], usize),
) -> (Vec<char>, Vec<HeaderViolation>) {
    let prefix_width: i64 =
        i64::try_from(HEADER_INDENT.len() + DESCRIPTION_KEY.len() + 2).unwrap_or(i64::MAX);
    let closing_width: i64 = 2;
    let description: Vec<char> = wrap_description(
        &chars(comment),
        (config.line_width - prefix_width - closing_width).max(1),
        (config.line_width - closing_width).max(1),
    );
    let limit: usize = config.max_description_lines;
    if line_count(&description) <= limit {
        return (description, Vec::new());
    }
    let fault: HeaderViolation = violation_at(
        &line_starts(text),
        header_start,
        (RULE_LEADING_COMMENT_DESCRIPTION, HeaderSeverity::Fault),
        (
            format!("Relocated leading comment exceeds {limit} lines"),
            format!("Shorten the relocated description to {limit} lines."),
        ),
    );
    (description, vec![fault])
}

/// The `description "..."` line inserted after a model header's opening parenthesis.
fn description_insertion(description: &[char]) -> Vec<char> {
    let escaped: String = string(description)
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace("\r\n", "\n");
    chars(&format!(
        "\n{HEADER_INDENT}{DESCRIPTION_KEY} \"{escaped}\","
    ))
}

/// A model header's leading comment moved into its description, with any length fault.
pub(crate) fn relocate_leading_comment<P: HeaderParser>(
    text: &[char],
    config: HeaderRulesConfig,
    headers: &[HeaderSpan],
    parser: &P,
) -> Result<(Vec<char>, Vec<HeaderViolation>), P::Error> {
    let unchanged = || (text.to_vec(), Vec::new());
    let Some(header) = headers.first().filter(|header| header.kind == MODEL_KIND) else {
        return Ok(unchanged());
    };
    let Some(comment) = leading_comment(slice(text, 0, header.start)) else {
        return Ok(unchanged());
    };
    let header_text: &[char] = slice(text, header.start, header.end);
    let values: P::Values =
        match parser.parse(&header.kind, &string(inner_header_text(header_text))) {
            ParseOutcome::Parsed(values) => values,
            ParseOutcome::Rejected(_) | ParseOutcome::Raised(..) => return Ok(unchanged()),
        };
    if parser.description(&values)?.is_some() {
        return Ok(unchanged());
    }
    let (description, faults) = relocated_description(&comment, config, (text, header.start));
    let insertion: Vec<char> = description_insertion(&description);
    let mut updated: Vec<char> = match header_text.iter().position(|character| *character == '(') {
        Some(open) => [&header_text[..=open], &insertion, &header_text[open + 1..]].concat(),
        None => header_text.to_vec(),
    };
    updated.extend(tail(text, header.end));
    Ok((updated, faults))
}

pub(crate) fn wrap_descriptions<P: HeaderParser>(
    text: &[char],
    headers: &[HeaderSpan],
    line_width: i64,
    parser: &P,
) -> Result<Vec<char>, P::Error> {
    let mut updated: Vec<char> = text.to_vec();
    for header in headers.iter().rev() {
        if !DESCRIPTION_HEADER_KINDS.contains(&header.kind.as_str()) {
            continue;
        }
        let header_text: Vec<char> = slice(&updated, header.start, header.end).to_vec();
        let Some((start, end)) = description_value_span(&header_text) else {
            continue;
        };
        let values: P::Values =
            match parser.parse(&header.kind, &string(inner_header_text(&header_text))) {
                ParseOutcome::Parsed(values) => values,
                ParseOutcome::Rejected(_) => continue,
                ParseOutcome::Raised(error, _) => return Err(error),
            };
        if parser.description(&values)?.is_none() {
            continue;
        }
        let quote: char = header_text[start - 1];
        let wrapped: Vec<char> = wrap_header_description(
            &decode_description(slice(&header_text, start, end), quote),
            &header_text,
            (start, end),
            line_width,
        );
        let rewritten: Vec<char> = [
            slice(&header_text, 0, start),
            &escape_quoted(&wrapped, quote),
            tail(&header_text, end),
        ]
        .concat();
        updated = [
            slice(&updated, 0, header.start),
            &rewritten,
            tail(&updated, header.end),
        ]
        .concat();
    }
    Ok(updated)
}

/// Whether two header texts parse to equal values; a header syntax error equals nothing.
fn same_values<P: HeaderParser>(
    kind: &str,
    (left, right): (&[char], &[char]),
    parser: &P,
) -> Result<bool, P::Error> {
    let parse = |text: &[char]| match parser.parse(kind, &string(inner_header_text(text))) {
        ParseOutcome::Parsed(values) => Ok(Some(values)),
        ParseOutcome::Rejected(_) => Ok(None),
        ParseOutcome::Raised(error, _) => Err(error),
    };
    let left: Option<P::Values> = parse(left)?;
    let right: Option<P::Values> = parse(right)?;
    match (left, right) {
        (Some(left), Some(right)) => parser.same(&left, &right),
        _ => Ok(false),
    }
}

pub(crate) fn wrap_audits<P: HeaderParser>(
    text: &[char],
    line_width: i64,
    parser: &P,
) -> Result<Vec<char>, P::Error> {
    let mut updated: Vec<char> = text.to_vec();
    for header in scan_headers(text, false).iter().rev() {
        let header_text: Vec<char> = slice(&updated, header.start, header.end).to_vec();
        let wrapped: Vec<char> = wrap_header(&header_text, line_width);
        if wrapped == header_text || !same_values(&header.kind, (&wrapped, &header_text), parser)? {
            continue;
        }
        updated = [
            slice(&updated, 0, header.start),
            &wrapped,
            tail(&updated, header.end),
        ]
        .concat();
    }
    Ok(updated)
}
