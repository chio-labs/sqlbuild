//! Native SQL lint responses mapped back onto authored source through expansion passes.

use std::sync::LazyLock;

use regex::Regex;
use serde_json::{Map, Value};

use crate::lint_text::_helpers::sites::compiled;
use crate::lint_text::constants::{
    GENERATED_FIX, GENERATED_SQL_SUFFIX, HARNESS_CTE_PREFIXES, INVALID_DIAGNOSTIC,
    INVALID_FIX_EDIT, INVALID_FIX_OBJECT, INVALID_FIX_REASON, LINT_API_VERSION, LONG_LITERAL_CODE,
    MISSING_DIAGNOSTICS, NATIVE_LINT_ERROR_CODE, NON_CONTIGUOUS_FIX, NON_OBJECT_RESPONSE,
    NOT_AN_OBJECT, PARSE_ERROR_POSITION_PATTERN, PARSE_FAILURE_PREFIX, PARSE_FAILURE_REMEDIATION,
    UNSUPPORTED_VERSION, UNUSED_CTE_CODE,
};
use crate::lint_text::main::interpolation_text_at::interpolation_text_at;
use crate::lint_text::models::{AuthoredDiagnostic, AuthoredEdit, ExpansionSpan, LintSqlBody};

static PARSE_ERROR_POSITION: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(PARSE_ERROR_POSITION_PATTERN));

/// One file's text as characters and line starts, and the dialect tokens are read in.
pub(crate) struct AuthoredFile<'a> {
    pub(crate) text: &'a str,
    pub(crate) characters: Vec<char>,
    pub(crate) line_starts: Vec<i64>,
    pub(crate) dialect: &'a str,
}

impl<'a> AuthoredFile<'a> {
    pub(crate) fn new(text: &'a str, dialect: &'a str) -> Self {
        let characters: Vec<char> = text.chars().collect();
        let mut line_starts: Vec<i64> = vec![0];
        line_starts.extend(
            characters
                .iter()
                .enumerate()
                .filter(|(_, character)| **character == '\n')
                .map(|(index, _)| index as i64 + 1),
        );
        Self {
            text,
            characters,
            line_starts,
            dialect,
        }
    }

    /// One-based line and column of a character offset.
    fn position(&self, offset: i64) -> (i64, i64) {
        let index: usize = self
            .line_starts
            .partition_point(|start| *start <= offset)
            .saturating_sub(1);
        (index as i64 + 1, offset - self.line_starts[index] + 1)
    }

    fn token_at(&self, offset: i64) -> Option<String> {
        match usize::try_from(offset) {
            Ok(start) => interpolation_text_at(self.text, start, self.dialect),
            Err(_) => None,
        }
    }

    fn starts_with_harness_cte(&self, offset: i64) -> bool {
        let Ok(start) = usize::try_from(offset) else {
            return false;
        };
        let rest: &[char] = self.characters.get(start..).unwrap_or_default();
        HARNESS_CTE_PREFIXES
            .iter()
            .any(|prefix| has_prefix(rest, prefix))
    }
}

fn has_prefix(rest: &[char], prefix: &str) -> bool {
    let expected: Vec<char> = prefix.chars().collect();
    rest.starts_with(&expected)
}

/// Map an expanded offset through one pass: the authored offset, and whether it was generated.
fn map_pass(offset: i64, spans: &[ExpansionSpan]) -> (i64, bool) {
    let mut mapped: i64 = offset;
    for span in spans {
        if offset < span.output_start {
            break;
        }
        if offset < span.output_end {
            return (span.source_start, true);
        }
        mapped += (span.source_end - span.source_start) - (span.output_end - span.output_start);
    }
    (mapped, false)
}

/// Map an expanded offset back through every pass, last pass first.
pub(crate) fn map_offset(offset: i64, passes: &[Vec<ExpansionSpan>]) -> (i64, bool) {
    let mut current: i64 = offset;
    let mut generated: bool = false;
    for spans in passes.iter().rev() {
        let (mapped, inside) = map_pass(current, spans);
        current = mapped;
        generated = generated || inside;
    }
    (current, generated)
}

/// The diagnostics list of one engine response, or the error it reports.
pub(crate) fn response_diagnostics(response: &Value) -> Result<Vec<Value>, String> {
    let Some(payload) = response.as_object() else {
        return Err(NON_OBJECT_RESPONSE.to_string());
    };
    if let Some(Value::String(message)) = payload.get("Err") {
        return Err(message.clone());
    }
    let Some(result) = payload.get("Ok").and_then(Value::as_object) else {
        return Err(NON_OBJECT_RESPONSE.to_string());
    };
    if integer(result.get("version")) != Some(LINT_API_VERSION) {
        return Err(UNSUPPORTED_VERSION.to_string());
    }
    match result.get("diagnostics") {
        Some(Value::Array(diagnostics)) => Ok(diagnostics.clone()),
        _ => Err(MISSING_DIAGNOSTICS.to_string()),
    }
}

/// A JSON integer, excluding floats and booleans.
fn integer(value: Option<&Value>) -> Option<i64> {
    match value {
        Some(Value::Number(number)) if number.is_i64() || number.is_u64() => number.as_i64(),
        _ => None,
    }
}

/// Keep diagnostics before an added `SELECT 1`, clamped to end there.
pub(crate) fn authored_prefix(diagnostics: Vec<Value>, offset: i64) -> Vec<Value> {
    let mut kept: Vec<Value> = Vec::new();
    for raw in diagnostics {
        let Value::Object(mut diagnostic) = raw else {
            kept.push(raw);
            continue;
        };
        if integer(diagnostic.get("start")).is_some_and(|start| start >= offset) {
            continue;
        }
        if integer(diagnostic.get("end")).is_some_and(|end| end > offset) {
            let _ = diagnostic.insert("end".to_string(), Value::from(offset));
        }
        let fix_end: Option<i64> = diagnostic
            .get("fix")
            .and_then(Value::as_object)
            .and_then(|fix| integer(fix.get("end")));
        if fix_end.is_some_and(|end| end > offset) {
            let _ = diagnostic.insert("fix".to_string(), Value::Null);
            let _ = diagnostic.insert(
                "fix_unavailable_reason".to_string(),
                Value::from(GENERATED_FIX),
            );
        }
        kept.push(Value::Object(diagnostic));
    }
    kept
}

/// The authored fault for a body the native parser rejected.
pub(crate) fn parse_failure(
    message: &str,
    body: &LintSqlBody,
    file: &AuthoredFile<'_>,
) -> AuthoredDiagnostic {
    let (line, column): (i64, i64) = parser_position(message);
    let lines: Vec<i64> = keepends_lengths(&body.lint_text);
    let mut expanded: i64 = 0;
    if line >= 1 && line as usize <= lines.len() {
        let index: usize = line as usize - 1;
        expanded = lines[..index].iter().sum::<i64>() + (column - 1).min(lines[index]);
    }
    let (mapped, _) = map_offset(expanded, &body.passes);
    let (line, column) = file.position(body.body_start + mapped);
    AuthoredDiagnostic {
        file: body.file,
        line,
        column,
        code: NATIVE_LINT_ERROR_CODE.to_string(),
        message: format!("{PARSE_FAILURE_PREFIX}{message}"),
        fault: true,
        end: None,
        remediation: PARSE_FAILURE_REMEDIATION.to_string(),
        fix: None,
        fix_unavailable_reason: None,
    }
}

/// The one-based line and column a parser error names, or `(1, 1)`.
fn parser_position(message: &str) -> (i64, i64) {
    let Ok(pattern) = compiled(&PARSE_ERROR_POSITION) else {
        return (1, 1);
    };
    let Some(captures) = pattern.captures(message) else {
        return (1, 1);
    };
    match (
        captures["line"].parse::<i64>(),
        captures["column"].parse::<i64>(),
    ) {
        (Ok(line), Ok(column)) => (line, column),
        _ => (1, 1),
    }
}

/// Character lengths of Python's `splitlines(keepends=True)` lines.
fn keepends_lengths(text: &str) -> Vec<i64> {
    crate::lint_text::_helpers::lines::line_spans(text)
        .iter()
        .map(|span| (span.end - span.start) as i64)
        .collect()
}

/// The fields of one native diagnostic, its span in lint-text characters.
struct DiagnosticFields {
    code: String,
    message: String,
    remediation: String,
    start: i64,
    end: i64,
}

/// The fields of one diagnostic: code, message, remediation, start and end.
fn diagnostic_fields(
    diagnostic: &Map<String, Value>,
    body_length: i64,
) -> Result<DiagnosticFields, String> {
    let text = |key: &str| {
        diagnostic
            .get(key)
            .and_then(Value::as_str)
            .map(str::to_string)
    };
    let (Some(code), Some(message), Some(remediation)) =
        (text("code"), text("message"), text("remediation"))
    else {
        return Err(INVALID_DIAGNOSTIC.to_string());
    };
    let (Some(start), Some(end)) = (
        integer(diagnostic.get("start")),
        integer(diagnostic.get("end")),
    ) else {
        return Err(INVALID_DIAGNOSTIC.to_string());
    };
    if start < 0 || end < start || end > body_length {
        return Err(INVALID_DIAGNOSTIC.to_string());
    }
    Ok(DiagnosticFields {
        code,
        message,
        remediation,
        start,
        end,
    })
}

/// Map one native diagnostic onto authored source, or drop it when it belongs to generated SQL.
pub(crate) fn authored_diagnostic(
    raw: &Value,
    body: &LintSqlBody,
    file: &AuthoredFile<'_>,
) -> Result<Option<AuthoredDiagnostic>, String> {
    let Some(diagnostic) = raw.as_object() else {
        return Err(NOT_AN_OBJECT.to_string());
    };
    let body_length: i64 = body.lint_text.chars().count() as i64;
    let DiagnosticFields {
        code,
        message,
        remediation,
        start,
        end,
    } = diagnostic_fields(diagnostic, body_length)?;
    let reason: Option<String> = match diagnostic.get("fix_unavailable_reason") {
        None | Some(Value::Null) => None,
        Some(Value::String(reason)) => Some(reason.clone()),
        Some(_) => return Err(INVALID_FIX_REASON.to_string()),
    };
    let (mapped, generated) = map_offset(start, &body.passes);
    let absolute: i64 = body.body_start + mapped;
    if code == LONG_LITERAL_CODE && generated
        || code == UNUSED_CTE_CODE && file.starts_with_harness_cte(absolute)
    {
        return Ok(None);
    }
    let (line, column) = file.position(absolute);
    let end_position: Option<(i64, i64)> =
        authored_end((start, end), (mapped, generated), body, file);
    let raw_fix: Option<&Value> = diagnostic.get("fix").filter(|fix| !fix.is_null());
    let fix: Option<AuthoredEdit> = match raw_fix {
        Some(raw_fix) => authored_fix(raw_fix, body_length, body)?,
        None => None,
    };
    let fix_unavailable_reason: Option<String> = if raw_fix.is_some() && fix.is_none() {
        Some(NON_CONTIGUOUS_FIX.to_string())
    } else {
        reason
    };
    let message: String = if generated {
        match file.token_at(absolute) {
            Some(token) => format!("{message} (in SQL generated by {token})"),
            None => format!("{message} {GENERATED_SQL_SUFFIX}"),
        }
    } else {
        message
    };
    Ok(Some(AuthoredDiagnostic {
        file: body.file,
        line,
        column,
        code,
        message,
        fault: false,
        end: end_position,
        remediation,
        fix,
        fix_unavailable_reason,
    }))
}

/// The authored exclusive end position, only when authored continuity is provable.
fn authored_end(
    (start, end): (i64, i64),
    mapped_start: (i64, bool),
    body: &LintSqlBody,
    file: &AuthoredFile<'_>,
) -> Option<(i64, i64)> {
    let absolute: i64 = body.body_start + mapped_start.0;
    if mapped_start.1 {
        let token: String = file.token_at(absolute)?;
        return Some(file.position(absolute + token.chars().count() as i64));
    }
    if end <= start {
        return None;
    }
    let (last, generated) = map_offset(end - 1, &body.passes);
    if generated || last - mapped_start.0 != end - start - 1 {
        return None;
    }
    Some(file.position(body.body_start + last + 1))
}

/// Map a native edit only when both boundaries remain contiguous authored source.
fn authored_fix(
    raw_fix: &Value,
    body_length: i64,
    body: &LintSqlBody,
) -> Result<Option<AuthoredEdit>, String> {
    let Some(payload) = raw_fix.as_object() else {
        return Err(INVALID_FIX_OBJECT.to_string());
    };
    let (Some(start), Some(end), Some(replacement)) = (
        integer(payload.get("start")),
        integer(payload.get("end")),
        payload.get("replacement").and_then(Value::as_str),
    ) else {
        return Err(INVALID_FIX_EDIT.to_string());
    };
    if start < 0 || end <= start || end > body_length {
        return Err(INVALID_FIX_EDIT.to_string());
    }
    let (mut region_start, mut region_end): (i64, i64) = (start, end);
    for spans in body.passes.iter().rev() {
        if spans
            .iter()
            .any(|span| overlaps(span, region_start, region_end))
        {
            return Ok(None);
        }
        region_start = map_pass(region_start, spans).0;
        region_end = map_pass(region_end, spans).0;
    }
    let (first, first_generated) = map_offset(start, &body.passes);
    let (last, last_generated) = map_offset(end - 1, &body.passes);
    if first_generated || last_generated || last - first != end - start - 1 {
        return Ok(None);
    }
    Ok(Some(AuthoredEdit {
        start: body.body_start + first,
        end: body.body_start + last + 1,
        replacement: replacement.to_string(),
    }))
}

fn overlaps(span: &ExpansionSpan, start: i64, end: i64) -> bool {
    start < span.output_end && span.output_start < end
        || span.output_start == span.output_end
            && start <= span.output_start
            && span.output_start < end
}
