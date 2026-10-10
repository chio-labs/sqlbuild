//! Python's `_explain_model`: schema evidence, suggestions and operand types for model errors.

use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use regex::Regex;

use crate::semantic_checks::_helpers::explanation::columns::{closest_column, ordered_columns};
use crate::semantic_checks::_helpers::explanation::messages::{
    comparison_help, missing_column, pattern, semantic_help, sentence_message, type_words,
};
use crate::semantic_checks::_helpers::sql_text::python_regex::{ignorecase_word, python_regex};
use crate::semantic_checks::_helpers::sql_text::text::{
    LineIndex, byte_offset, code_point_offset, last_newline_before, newlines_before, prefix, upper,
};
use crate::semantic_checks::constants::{
    COMPARISON_CODE, DECIMAL_OPERAND_PATTERN, DISPLAY_LIMIT, INTEGER_OPERAND_PATTERN,
    OPERAND_PATTERN, QUALIFIER_PATTERN, TEMPORAL_OPERAND_PATTERN, TYPE_CODES, UNKNOWN_COLUMN_CODE,
};
use crate::semantic_checks::models::{CompletedDiagnostic, SemanticFailure, SemanticLocation};

/// A diagnostic located past the model's authored lines, where Python raised `IndexError`.
const OUTSIDE_AUTHORED_LINES: &str = "a diagnostic line outside the model's authored SQL";

static QUALIFIER: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| python_regex(QUALIFIER_PATTERN));
static BINARY: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    let operand: String = operand_template();
    python_regex(&format!(
        r"(?P<left>{operand}){{S}}*(?:>=|<=|<>|!=|=|>|<|\+|\*|/|-){{S}}*(?P<right>{operand})"
    ))
});
static OPERAND_AT: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| python_regex(&format!(r"\A{}", operand_template())));
static TEMPORAL_OPERAND: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| python_regex(&temporal_words(TEMPORAL_OPERAND_PATTERN)));
static INTEGER_OPERAND: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| python_regex(INTEGER_OPERAND_PATTERN));
static DECIMAL_OPERAND: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| python_regex(DECIMAL_OPERAND_PATTERN));

/// `TIMESTAMP` and `DATE` in a template, as Python's `re.IGNORECASE` matches them.
fn temporal_words(template: &str) -> String {
    template
        .replace("{TIMESTAMP}", &ignorecase_word("TIMESTAMP"))
        .replace("{DATE}", &ignorecase_word("DATE"))
}

fn operand_template() -> String {
    temporal_words(OPERAND_PATTERN)
}

/// Closed relation shapes by name, each in Python's dict order.
pub(crate) type Shapes<'a> = HashMap<&'a str, &'a [(String, String)]>;

/// Python's `_TYPE_CODES`: B210 to B219.
pub(crate) fn is_type_code(code: &str) -> bool {
    TYPE_CODES.contains(&code)
}

/// One binary operation Python's `_BINARY` finds in authored SQL.
pub(crate) struct Binary {
    start: usize,
    end: usize,
    left: String,
    right: String,
}

/// Python's `_binary_index`: every binary operation in authored SQL, in order.
pub(crate) fn binary_index(sql: &str) -> Result<Vec<Binary>, SemanticFailure> {
    let binary: &Regex = pattern(&BINARY)?;
    let mut found: Vec<Binary> = Vec::new();
    for captures in binary.captures_iter(sql) {
        let (start, end) = captures.get(0).map_or((0, 0), |item| {
            (
                code_point_offset(sql, item.start()),
                code_point_offset(sql, item.end()),
            )
        });
        found.push(Binary {
            start,
            end,
            left: captures["left"].to_owned(),
            right: captures["right"].to_owned(),
        });
    }
    Ok(found)
}

/// What `_explain_model` reads about the model a diagnostic belongs to.
pub(crate) struct ModelEvidence<'a> {
    pub(crate) authored_sql: &'a str,
    pub(crate) aliases: &'a HashMap<String, String>,
    pub(crate) lines: &'a LineIndex<'a>,
    pub(crate) binaries: &'a [Binary],
}

/// Everything `_explain_model` reads beside the diagnostic itself.
pub(crate) struct ExplainContext<'a> {
    pub(crate) code: &'a str,
    pub(crate) model: &'a ModelEvidence<'a>,
    pub(crate) shapes: &'a Shapes<'a>,
    pub(crate) dialect: Option<&'a str>,
}

/// One model diagnostic rewritten with Python's explanation.
pub(crate) fn explain_model(
    diagnostic: &CompletedDiagnostic,
    context: &ExplainContext<'_>,
) -> Result<CompletedDiagnostic, SemanticFailure> {
    let ExplainContext {
        code,
        model,
        shapes,
        dialect,
    } = *context;
    let original: String = diagnostic.message.clone();
    let mut message: String = sentence_message(&original)?;
    let mut help: Option<String> = semantic_help(code).map(str::to_owned);
    if code == COMPARISON_CODE {
        help = Some(comparison_help(&type_words(&original)?, dialect));
    }
    let mut notes: Vec<String> = diagnostic.notes.clone();
    let mut location: Option<SemanticLocation> = diagnostic.location;
    if let Some((name, table)) = missing_column(&original)? {
        let columns: &[(String, String)] = shapes
            .get(table.as_deref().unwrap_or(""))
            .copied()
            .unwrap_or_default();
        help = closest_column(&name, columns)?
            .filter(|suggestion| !suggestion.is_empty())
            .map(|suggestion| format!("did you mean '{suggestion}'?"));
        message = format!("Unknown column '{name}'");
        if let Some(table) = &table {
            message.push_str(&format!(" in {table}"));
        }
        if let Some(location) = &location {
            let line: &str = python_line(model.lines, location.line)?;
            if let Some(alias) = qualifier(prefix(line, location.column - 1))?
                && model.aliases.get(&alias) == table.as_ref()
            {
                message.push_str(&format!(" (as {alias})"));
            }
        }
        let available: Vec<&str> = ordered_columns(&name, columns)?;
        if !available.is_empty() {
            let suffix: String = if available.len() > DISPLAY_LIMIT {
                format!(", and {} more", available.len() - DISPLAY_LIMIT)
            } else {
                String::new()
            };
            let shown: Vec<&str> = available.iter().take(DISPLAY_LIMIT).copied().collect();
            notes.insert(
                0,
                format!(
                    "{} has: {}{suffix}",
                    table.as_deref().unwrap_or("None"),
                    shown.join(", ")
                ),
            );
        }
    }
    if is_type_code(code)
        && let Some(current) = location
    {
        let offset: i64 = model.lines.offset(current.line, current.column);
        match binary_at(model.binaries, offset) {
            Some(binary) => {
                let left = operand_type(&binary.left, model.aliases, shapes)?;
                let right = operand_type(&binary.right, model.aliases, shapes)?;
                if let (Some(left_type), Some(right_type)) = (&left, &right) {
                    notes.push(format!(
                        "{} is {left_type}, {} is {right_type}",
                        binary.left, binary.right
                    ));
                    if code == COMPARISON_CODE {
                        help = Some(comparison_help(
                            &[left_type.clone(), right_type.clone()],
                            dialect,
                        ));
                    }
                }
                let mut end: i64 = position(binary.end);
                if let (Some(end_line), Some(end_column)) = (current.end_line, current.end_column) {
                    end = end.max(model.lines.offset(end_line, end_column));
                }
                let begin: i64 = position(binary.start).min(offset);
                let sql = model.authored_sql;
                location = Some(SemanticLocation {
                    line: newlines_before(sql, begin) + 1,
                    column: begin - last_newline_before(sql, begin),
                    end_line: Some(newlines_before(sql, end) + 1),
                    end_column: Some(end - last_newline_before(sql, end)),
                });
            }
            None => {
                if let Some(operand) = operand_at(model.authored_sql, offset)?
                    && let Some(kind) = operand_type(operand, model.aliases, shapes)?
                {
                    notes.push(format!("{operand} is {kind}"));
                }
            }
        }
    }
    Ok(CompletedDiagnostic {
        source: diagnostic.source,
        message,
        help,
        notes,
        location,
        line: location.map_or(diagnostic.line, |current| Some(current.line)),
        column: location.map_or(diagnostic.column, |current| Some(current.column)),
        changed: true,
    })
}

/// True when `code` is one `_explain_model` rewrites.
pub(crate) fn is_explained_code(code: &str) -> bool {
    code == UNKNOWN_COLUMN_CODE || is_type_code(code)
}

fn position(offset: usize) -> i64 {
    i64::try_from(offset).unwrap_or(i64::MAX)
}

/// Python's `lines[line - 1]`, including its negative indexing; out of range is internal.
fn python_line<'a>(lines: &'a LineIndex<'a>, line: i64) -> Result<&'a str, SemanticFailure> {
    let count: i64 = i64::try_from(lines.lines.len()).unwrap_or(i64::MAX);
    let index: i64 = if line - 1 < 0 {
        line - 1 + count
    } else {
        line - 1
    };
    match usize::try_from(index) {
        Ok(index) => lines
            .lines
            .get(index)
            .copied()
            .ok_or_else(|| SemanticFailure::internal(OUTSIDE_AUTHORED_LINES)),
        Err(_) => Err(SemanticFailure::internal(OUTSIDE_AUTHORED_LINES)),
    }
}

/// The alias qualifying the column that ends `prefix`, with doubled quotes undone.
fn qualifier(prefix: &str) -> Result<Option<String>, SemanticFailure> {
    let Some(captures) = pattern(&QUALIFIER)?.captures(prefix) else {
        return Ok(None);
    };
    let alias: String = match (captures.get(1), captures.get(2)) {
        (Some(quoted), _) => quoted.as_str().replace("\"\"", "\""),
        (None, Some(plain)) => plain.as_str().to_owned(),
        (None, None) => String::new(),
    };
    Ok((!alias.is_empty()).then_some(alias))
}

/// Python's `_binary_at`: the last operation starting at or before `offset`, if it covers it.
fn binary_at(binaries: &[Binary], offset: i64) -> Option<&Binary> {
    let count = binaries.partition_point(|binary| position(binary.start) <= offset);
    let binary = binaries.get(count.checked_sub(1)?)?;
    (offset < position(binary.end)).then_some(binary)
}

/// Python's `re.compile(_OPERAND, re.IGNORECASE).match(sql, offset)`.
fn operand_at(sql: &str, offset: i64) -> Result<Option<&str>, SemanticFailure> {
    let operand: &Regex = pattern(&OPERAND_AT)?;
    let start: usize = usize::try_from(offset.max(0)).unwrap_or(usize::MAX);
    if start > sql.chars().count() {
        return Ok(None);
    }
    Ok(operand
        .find(&sql[byte_offset(sql, start)..])
        .map(|found| found.as_str()))
}

/// Python's `_operand_type`.
fn operand_type(
    text: &str,
    aliases: &HashMap<String, String>,
    shapes: &Shapes<'_>,
) -> Result<Option<String>, SemanticFailure> {
    if let Some(captures) = pattern(&TEMPORAL_OPERAND)?.captures(text) {
        return Ok(Some(upper(&captures[1])));
    }
    if pattern(&INTEGER_OPERAND)?.is_match(text) {
        return Ok(Some("INTEGER".to_owned()));
    }
    if pattern(&DECIMAL_OPERAND)?.is_match(text) {
        return Ok(Some("DECIMAL".to_owned()));
    }
    if text.starts_with('\'') {
        return Ok(Some("VARCHAR".to_owned()));
    }
    if let Some((alias, column)) = text.split_once('.') {
        let table: &str = aliases.get(alias).map_or(alias, String::as_str);
        let value = shape_type(shapes, table, column);
        return match value {
            Some(value) if !value.is_empty() => Ok(Some(upper(value))),
            _ => Ok(None),
        };
    }
    let tables: HashSet<&str> = aliases.values().map(String::as_str).collect();
    let mut candidates: HashSet<String> = HashSet::new();
    for table in tables {
        if let Some(value) = shape_type(shapes, table, text) {
            candidates.insert(upper(value));
        }
    }
    Ok(if candidates.len() == 1 {
        candidates
            .into_iter()
            .next()
            .filter(|value| !value.is_empty())
    } else {
        None
    })
}

fn shape_type<'a>(shapes: &Shapes<'a>, table: &str, column: &str) -> Option<&'a str> {
    let shape: &'a [(String, String)] = shapes.get(table)?;
    for (name, value) in shape {
        if name == column {
            return Some(value.as_str());
        }
    }
    None
}
