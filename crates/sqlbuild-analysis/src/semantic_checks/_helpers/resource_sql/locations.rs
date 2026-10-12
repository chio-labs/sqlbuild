//! Python's `_location` and the authored text a resource SQL finding quotes.

use sqlbuild_core::text::main::ignorecase_key::ignorecase_key;

use crate::semantic_checks::_helpers::resource_sql::resources::{ResourceSql, find_code_points};
use crate::semantic_checks::_helpers::resource_sql::scanning::word_at;
use crate::semantic_checks::models::ResourceSqlFailure;
use crate::semantic_validation::models::{BindingPositions, PositionInput};

/// A binding finding: code, message, line, column, start, end and severity.
pub(crate) type Finding = (
    String,
    String,
    Option<usize>,
    Option<usize>,
    Option<usize>,
    Option<usize>,
    String,
);

/// `(line, column, end line, end column)`.
pub(crate) type Span = (i64, i64, Option<i64>, Option<i64>);

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
) -> Result<Option<Span>, ResourceSqlFailure> {
    let mapper = BindingPositions::new(PositionInput {
        authored: resource.contents.to_string(),
        query: resource.authored_body.clone(),
        expanded: resource.sql.clone(),
        cleaned: cleaned_sql.to_owned(),
        passes: Vec::new(),
    })
    .map_err(ResourceSqlFailure::Normalization)?;
    let (line, column) = mapper
        .position(finding.4, finding.2, finding.3, &finding.1)
        .map_err(ResourceSqlFailure::Normalization)?;
    let (Some(line), Some(column)) = (line, column) else {
        return Ok(None);
    };
    let (end_line, end_column) = match finding.5 {
        Some(end) => mapper
            .position(Some(end), None, None, "")
            .map_err(ResourceSqlFailure::Normalization)?,
        None => (None, None),
    };
    Ok(Some((
        line as i64,
        column as i64,
        usize_line(end_line),
        usize_line(end_column),
    )))
}

/// Python's `_location`: the offending authored text, falling back to the body start.
pub(crate) fn location(
    resource: &ResourceSql,
    cleaned_sql: &str,
    finding: &Finding,
) -> Result<Span, ResourceSqlFailure> {
    let body_offset = find_code_points(&resource.contents, &resource.authored_body).unwrap_or(0);
    if finding.4.is_none() {
        let text: Vec<char> = resource.contents.chars().collect();
        if let Some(offset) = quoted_name_offset(&text, body_offset, &finding.1) {
            let (line, column) = offset_location(&resource.contents, offset);
            return Ok((line, column, None, None));
        }
    }
    if let Some(span) = mapped_span(resource, cleaned_sql, finding)? {
        return Ok(span);
    }
    let (line, column) = offset_location(&resource.contents, body_offset);
    Ok((line, column, None, None))
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
pub(crate) fn text_from(resource: &ResourceSql, span: Span) -> String {
    let starts = line_starts(&resource.contents);
    let Some(start) = offset(&starts, span.0, span.1) else {
        return String::new();
    };
    let end = match (span.2, span.3) {
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
pub(crate) fn line_at(resource: &ResourceSql, span: Span) -> String {
    let lines: Vec<&str> = resource.contents.lines().collect();
    if span.0 < 1 {
        return String::new();
    }
    lines
        .get((span.0 - 1) as usize)
        .map_or_else(String::new, |line| (*line).to_owned())
}
