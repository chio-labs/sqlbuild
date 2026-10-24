//! Header formatting fixes: trailing spaces, leading comments, description and audit wrapping.

use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::dsl_headers::_helpers::audits::wrap_header;
use sqlbuild_sqltext::header_strings::constants::TRIPLE_QUOTE;
use sqlbuild_sqltext::header_strings::main::fold_prose::fold_prose;
use sqlbuild_sqltext::header_strings::main::follows_description_key::follows_description_key;
use sqlbuild_sqltext::header_strings::main::prose_string::prose_string;

use crate::dsl_headers::_helpers::macro_header::same_macro;
use crate::dsl_headers::_helpers::prose_layout::{
    canonical_prose, closing_width, description_string_span,
};
use crate::dsl_headers::_helpers::quoted::{description_value_spans, split_outside_quotes};
use crate::dsl_headers::_helpers::rules::violation_at;
use crate::dsl_headers::_helpers::text::{
    chars, find, line_count, line_starts, lstrip, rfind_before, rstrip, slice, string, tail,
};
use crate::dsl_headers::_helpers::wrap::wrap_description;
use crate::dsl_headers::constants::{
    DESCRIPTION_KEY, HEADER_INDENT, MODEL_KIND, RULE_LEADING_COMMENT_DESCRIPTION,
    SQL_MACRO_HEADER_KIND,
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

/// The `description` line inserted after a model header's `(`, if the comment can be quoted.
fn description_insertion(description: &[char]) -> Option<Vec<char>> {
    let value: String = fold_prose(&string(description));
    if value.contains(TRIPLE_QUOTE) {
        return None;
    }
    let quoted: String = if value.contains('"') {
        format!("{TRIPLE_QUOTE}{value}{TRIPLE_QUOTE}")
    } else {
        format!("\"{value}\"")
    };
    Some(chars(&format!(
        "\n{HEADER_INDENT}{DESCRIPTION_KEY} {quoted},"
    )))
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
    let Some(insertion) = description_insertion(&description) else {
        return Ok(unchanged());
    };
    let mut updated: Vec<char> = match header_text.iter().position(|character| *character == '(') {
        Some(open) => [&header_text[..=open], &insertion, &header_text[open + 1..]].concat(),
        None => header_text.to_vec(),
    };
    updated.extend(tail(text, header.end));
    Ok((updated, faults))
}

/// Every top-level description of `headers` of the `kinds` in its canonical layout.
pub(crate) fn wrap_descriptions<P: HeaderParser>(
    text: &[char],
    headers: &[HeaderSpan],
    (kinds, line_width): (&[&str], i64),
    parser: &P,
) -> Result<Vec<char>, P::Error> {
    let mut updated: Vec<char> = text.to_vec();
    for header in headers.iter().rev() {
        if !kinds.contains(&header.kind.as_str()) {
            continue;
        }
        let header_text: Vec<char> = slice(&updated, header.start, header.end).to_vec();
        let Some(rewritten) = laid_out_description(&header.kind, &header_text, line_width, parser)?
        else {
            continue;
        };
        let candidate: Vec<char> = [
            slice(&updated, 0, header.start),
            &rewritten,
            tail(&updated, header.end),
        ]
        .concat();
        if header.kind == SQL_MACRO_HEADER_KIND && !same_macro(&updated, &candidate) {
            continue;
        }
        updated = candidate;
    }
    Ok(updated)
}

/// Every column and audit description of `headers` of the `kinds` in its canonical layout.
pub(crate) fn wrap_nested_descriptions<P: HeaderParser>(
    text: &[char],
    headers: &[HeaderSpan],
    (kinds, line_width): (&[&str], i64),
    parser: &P,
) -> Result<Vec<char>, P::Error> {
    let mut updated: Vec<char> = text.to_vec();
    for header in headers.iter().rev() {
        if !kinds.contains(&header.kind.as_str()) {
            continue;
        }
        let mut header_text: Vec<char> = slice(&updated, header.start, header.end).to_vec();
        let nested: Vec<usize> = description_value_spans(&header_text)
            .into_iter()
            .filter(|(_, depth)| *depth > 1)
            .map(|((value_start, _), _)| value_start - 1)
            .collect();
        for start in nested.into_iter().rev() {
            if let Some(rewritten) =
                laid_out_string(&header.kind, &header_text, start, (line_width, parser))?
            {
                header_text = rewritten;
            }
        }
        updated = [
            slice(&updated, 0, header.start),
            &header_text,
            tail(&updated, header.end),
        ]
        .concat();
    }
    Ok(updated)
}

/// `header_text` with the prose string at `start` laid out canonically, or `None` if unchanged.
fn laid_out_string<P: HeaderParser>(
    kind: &str,
    header_text: &[char],
    start: usize,
    (line_width, parser): (i64, &P),
) -> Result<Option<Vec<char>>, P::Error> {
    if !follows_description_key(header_text, start) {
        return Ok(None);
    }
    let Ok(prose) = prose_string(header_text, start) else {
        return Ok(None);
    };
    let end: usize = prose.end;
    if header_text[start] == '\'' && keeps_single_quotes(header_text, (start, end), line_width) {
        return Ok(None);
    }
    let Some(rendered) = canonical_prose(&prose.value, header_text, (start, end), line_width)
    else {
        return Ok(None);
    };
    if chars(&rendered) == slice(header_text, start, end) {
        return Ok(None);
    }
    let rewritten: Vec<char> = [
        slice(header_text, 0, start),
        &chars(&rendered),
        tail(header_text, end),
    ]
    .concat();
    if kind != SQL_MACRO_HEADER_KIND && !same_values(kind, (&rewritten, header_text), parser)? {
        return Ok(None);
    }
    Ok(Some(rewritten))
}

/// `header_text` with its description laid out canonically, or `None` when nothing changes.
fn laid_out_description<P: HeaderParser>(
    kind: &str,
    header_text: &[char],
    line_width: i64,
    parser: &P,
) -> Result<Option<Vec<char>>, P::Error> {
    let Some((start, _)) = description_string_span(header_text) else {
        return Ok(None);
    };
    laid_out_string(kind, header_text, start, (line_width, parser))
}

/// Whether a `'...'` description stays as written: on one line that fits, with no double quote.
fn keeps_single_quotes(
    header_text: &[char],
    (start, end): (usize, usize),
    line_width: i64,
) -> bool {
    let authored: &[char] = slice(header_text, start, end);
    if authored.contains(&'\n') || authored.contains(&'"') {
        return false;
    }
    let line_start: usize = rfind_before(header_text, '\n', start).map_or(0, |found| found + 1);
    let line_end: usize = find(header_text, &['\n'], end).unwrap_or(header_text.len());
    let width: usize = end - line_start + closing_width(slice(header_text, end, line_end));
    i64::try_from(width).is_ok_and(|width| width <= line_width)
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
