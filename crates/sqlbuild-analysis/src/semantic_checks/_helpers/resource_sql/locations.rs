//! Python's `_location` and the authored text a resource SQL finding quotes.

use sqlbuild_core::text::main::ignorecase_key::ignorecase_key;

use crate::semantic_checks::_helpers::resource_sql::resources::{ResourceSql, find_code_points};
use crate::semantic_checks::_helpers::resource_sql::scanning::word_at;
use crate::semantic_checks::models::{ResourceSpan, ResourceSqlFailure};
use crate::semantic_validation::main::truth_test_spans::truth_test_spans;
use crate::semantic_validation::models::{BindingPositions, DiagnosticRow, PositionInput};

/// A binding finding: code, message, cleaned position and severity.
pub(crate) type Finding = DiagnosticRow;

const UNSUPPORTED_TRUTH_TEST_CODE: &str = "B103";

/// Python's `_offset_location`: the 1-based line and column of a code-point offset.
pub(crate) fn offset_location(text: &str, offset: usize) -> (i64, i64) {
    let before: Vec<char> = text.chars().take(offset).collect();
    let line = before
        .iter()
        .filter(|character| **character == '\n')
        .count() as i64
        + 1;
    let line_start = before
        .iter()
        .rposition(|character| *character == '\n')
        .map_or(0, |index| index + 1);
    (line, (offset - line_start) as i64 + 1)
}

/// The single-quoted pieces of `message`, as `'([^']+)'` finds them.
fn quoted_names(message: &str) -> Vec<&str> {
    let mut names: Vec<&str> = Vec::new();
    let mut rest = message;
    while let Some(open) = rest.find('\'') {
        let after = &rest[open + 1..];
        match after.find('\'') {
            Some(0) => rest = after,
            Some(close) => {
                names.push(&after[..close]);
                rest = &after[close + 1..];
            }
            None => break,
        }
    }
    names
}

/// `(?<!\w)identifier(?!\w)`, ignoring case, in `text[start..]`: its code-point offset.
fn word_offset(text: &[char], start: usize, identifier: &[char]) -> Option<usize> {
    let key = |character: &char| ignorecase_key(*character);
    let keys: Vec<char> = identifier.iter().map(key).collect();
    let last = text.len().checked_sub(identifier.len())?;
    (start..=last).find(|position| {
        (*position == start || !word_at(text, Some(position - 1)))
            && text[*position..position + identifier.len()]
                .iter()
                .map(key)
                .eq(keys.iter().copied())
            && !word_at(text, Some(position + identifier.len()))
    })
}

/// Python's `_quoted_name_offset`: where a name the message quotes first occurs in the body.
fn quoted_name_offset(text: &[char], start: usize, message: &str) -> Option<usize> {
    quoted_names(message).into_iter().find_map(|name| {
        let identifier: Vec<char> = name.rsplit('.').next().unwrap_or(name).chars().collect();
        word_offset(text, start.min(text.len()), &identifier)
    })
}

fn usize_line(value: Option<usize>) -> Option<i64> {
    value.map(|value| value as i64)
}

/// Python's `get_authored_binding_location` for a resource body, without expansion passes.
fn mapped_span(
    resource: &ResourceSql,
    cleaned_sql: &str,
    finding: &Finding,
) -> Result<Option<ResourceSpan>, ResourceSqlFailure> {
    let mapper = BindingPositions::new(PositionInput {
        authored: resource.contents.to_string(),
        query: resource.authored_body.clone(),
        expanded: resource.sql.clone(),
        cleaned: cleaned_sql.to_owned(),
        passes: Vec::new(),
    })
    .map_err(ResourceSqlFailure::Normalization)?;
    let (line, column) = mapper
        .position(
            finding.start,
            finding.line,
            finding.column,
            &finding.message,
        )
        .map_err(ResourceSqlFailure::Normalization)?;
    let (Some(line), Some(column)) = (line, column) else {
        return Ok(None);
    };
    let (end_line, end_column) = match finding.end {
        Some(end) => mapper
            .position(Some(end), None, None, "")
            .map_err(ResourceSqlFailure::Normalization)?,
        None => (None, None),
    };
    Ok(Some(ResourceSpan {
        line: line as i64,
        column: column as i64,
        end_line: usize_line(end_line),
        end_column: usize_line(end_column),
    }))
}

/// The authored span of the truth-value test a B103 finding starts at, matched by its order.
fn truth_test_span(
    resource: &ResourceSql,
    cleaned_sql: &str,
    start: usize,
) -> Option<ResourceSpan> {
    let cleaned: Vec<(usize, usize)> = truth_test_spans(cleaned_sql);
    let order: usize = cleaned
        .iter()
        .position(|(test_start, _)| cleaned_sql[..*test_start].chars().count() == start)?;
    let authored: Vec<(usize, usize)> = truth_test_spans(&resource.authored_body);
    if authored.len() != cleaned.len() {
        return None;
    }
    let (test_start, test_end) = *authored.get(order)?;
    let body_offset: usize = find_code_points(&resource.contents, &resource.authored_body)?;
    let offset: usize = body_offset + resource.authored_body[..test_start].chars().count();
    let length: usize = resource.authored_body[test_start..test_end].chars().count();
    let (line, column) = offset_location(&resource.contents, offset);
    let (end_line, end_column) = offset_location(&resource.contents, offset + length);
    Some(ResourceSpan {
        line,
        column,
        end_line: Some(end_line),
        end_column: Some(end_column),
    })
}

/// Python's `_location`: the offending authored text, falling back to the body start.
pub(crate) fn location(
    resource: &ResourceSql,
    cleaned_sql: &str,
    finding: &Finding,
) -> Result<ResourceSpan, ResourceSqlFailure> {
    let body_offset = find_code_points(&resource.contents, &resource.authored_body).unwrap_or(0);
    if finding.start.is_none() {
        let text: Vec<char> = resource.contents.chars().collect();
        if let Some(offset) = quoted_name_offset(&text, body_offset, &finding.message) {
            let (line, column) = offset_location(&resource.contents, offset);
            return Ok(ResourceSpan::start(line, column));
        }
    }
    if finding.code == UNSUPPORTED_TRUTH_TEST_CODE
        && let Some(span) = finding
            .start
            .and_then(|start| truth_test_span(resource, cleaned_sql, start))
    {
        return Ok(span);
    }
    if let Some(span) = mapped_span(resource, cleaned_sql, finding)? {
        return Ok(span);
    }
    let (line, column) = offset_location(&resource.contents, body_offset);
    Ok(ResourceSpan::start(line, column))
}

/// Code-point starts of each line of `text`.
fn line_starts(text: &str) -> Vec<usize> {
    text.lines()
        .map(|line| {
            text[..line.as_ptr() as usize - text.as_ptr() as usize]
                .chars()
                .count()
        })
        .collect()
}

/// Python's `_offset`: the code-point offset of a 1-based line and column, if the line exists.
fn offset(starts: &[usize], line: i64, column: i64) -> Option<usize> {
    if line < 1 {
        return None;
    }
    starts
        .get((line - 1) as usize)
        .map(|start| start + (column - 1).max(0) as usize)
}

/// Python's `_text_from`: the authored text of a span, or from its start.
pub(crate) fn text_from(resource: &ResourceSql, span: ResourceSpan) -> String {
    let starts = line_starts(&resource.contents);
    let Some(start) = offset(&starts, span.line, span.column) else {
        return String::new();
    };
    let end = match (span.end_line, span.end_column) {
        (Some(line), Some(column)) => offset(&starts, line, column),
        _ => None,
    };
    let characters = resource.contents.chars().skip(start);
    match end.filter(|end| *end > start) {
        Some(end) => characters.take(end - start).collect(),
        None => characters.collect(),
    }
}

/// Python's `_line_at`: the authored line of a span, or empty text.
pub(crate) fn line_at(resource: &ResourceSql, span: ResourceSpan) -> String {
    let lines: Vec<&str> = resource.contents.lines().collect();
    if span.line < 1 {
        return String::new();
    }
    lines
        .get((span.line - 1) as usize)
        .map_or_else(String::new, |line| (*line).to_owned())
}
