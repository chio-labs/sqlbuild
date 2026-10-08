//! The top-level CTE scan of Python `extract_top_level_ctes_with_scanner`, reproduced exactly.

use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_sqltext::sql_scan::main::dialect_matching_paren::dialect_matching_paren;
use sqlbuild_sqltext::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use sqlbuild_sqltext::sql_scan::models::{LexicalSyntax, Unclosed};
use std::collections::HashSet;

use crate::relationship_names::models::RelationshipSource;

/// Why the scan stopped before Python's result.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Stop {
    /// Python raises this message.
    Failed(String),
    /// Python's `str` classification or parenthesis matcher could read the text differently.
    Deferred,
}

type Scan<T> = Result<T, Stop>;

const EXPECTED_PREFIX: &str = "__expected__";
const QUOTE_TOKENS: &[u8] = b"'\"`$";
/// Python's parenthesis matcher only looks for comments at these characters.
const PAREN_SCAN_SPECIALS: &[u8] = b"-/#'\"`$()";

/// The authored text the scan reads, with the labels Python's messages name it by.
pub(crate) struct ScanText<'sql> {
    pub(crate) sql: &'sql str,
    pub(crate) file: &'sql str,
    pub(crate) source: RelationshipSource,
}

/// Return the expected-model names of one SQL test or scenario body.
pub(crate) fn expected_names(text: &ScanText<'_>, syntax: &LexicalSyntax) -> Scan<Vec<String>> {
    let sql = text.sql.as_bytes();
    let start = skip_ignorable(sql, 0, text, syntax)?;
    if try_consume_keyword(sql, start, b"WITH")?.is_none() {
        return Ok(Vec::new());
    }
    let ctes = top_level_ctes(text, syntax)?;
    ctes.into_iter()
        .filter_map(|(name, _)| name.strip_prefix(EXPECTED_PREFIX).map(str::to_owned))
        .map(|model| {
            if model.is_empty() {
                Err(Stop::Failed(format!(
                    "{} '{}' must use __expected__<model> to identify a target",
                    context_label(text.source),
                    text.file
                )))
            } else {
                Ok(model)
            }
        })
        .collect()
}

/// Return the top-level CTE names and stripped bodies, then check only `SELECT 1` follows.
pub(crate) fn top_level_ctes(
    text: &ScanText<'_>,
    syntax: &LexicalSyntax,
) -> Scan<Vec<(String, String)>> {
    if !syntax.line_comment_prefixes.iter().all(|prefix| {
        prefix.is_ascii()
            && prefix
                .as_bytes()
                .first()
                .is_some_and(|first| PAREN_SCAN_SPECIALS.contains(first))
    }) {
        return Err(Stop::Deferred);
    }
    let sql = text.sql.as_bytes();
    let with_end = try_consume_keyword(sql, skip_ignorable(sql, 0, text, syntax)?, b"WITH")?
        .ok_or_else(|| {
            failed(
                text,
                format!(
                    "must declare {} in a top-level WITH clause",
                    with_requirement(text.source)
                ),
            )
        })?;
    let mut index = skip_ignorable(sql, with_end, text, syntax)?;
    if let Some(recursive_end) = try_consume_keyword(sql, index, b"RECURSIVE")? {
        index = skip_ignorable(sql, recursive_end, text, syntax)?;
    }
    let mut ctes: Vec<(String, String)> = Vec::new();
    let mut seen: HashSet<&str> = HashSet::new();
    loop {
        let (name, name_end) = read_identifier(text, index)?;
        if !seen.insert(name) {
            return Err(failed(text, format!("defines duplicate CTE '{name}'")));
        }
        index = skip_ignorable(sql, name_end, text, syntax)?;
        if sql.get(index) == Some(&b'(') {
            index = matching_paren(text, index, syntax)? + 1;
            index = skip_ignorable(sql, index, text, syntax)?;
        }
        index = try_consume_keyword(sql, index, b"AS")?
            .ok_or_else(|| failed(text, "expected keyword AS".to_owned()))?;
        index = skip_ignorable(sql, index, text, syntax)?;
        if sql.get(index) != Some(&b'(') {
            return Err(failed(text, format!("CTE '{name}' must use AS (...)")));
        }
        let body_end = matching_paren(text, index, syntax)?;
        ctes.push((
            name.to_owned(),
            python_strip(&text.sql[index + 1..body_end]).to_owned(),
        ));
        index = skip_ignorable(sql, body_end + 1, text, syntax)?;
        if sql.get(index) == Some(&b',') {
            index = skip_ignorable(sql, index + 1, text, syntax)?;
            continue;
        }
        if trailing_statement_end(sql, index, text, syntax)?
            || trailing_ceremonial_select(sql, index, text, syntax)?
        {
            return Ok(ctes);
        }
        return Err(failed(
            text,
            "must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow \
             them"
                .to_owned(),
        ));
    }
}

fn context_label(source: RelationshipSource) -> &'static str {
    match source {
        RelationshipSource::Test => "SQL test",
        RelationshipSource::Scenario => "SQL scenario",
    }
}

fn with_requirement(source: RelationshipSource) -> &'static str {
    match source {
        RelationshipSource::Test => "mock CTEs and one __expected__<model> CTE",
        RelationshipSource::Scenario => {
            "fixture CTEs and at least one __expected__<model> or __assert__<assertion> CTE"
        }
    }
}

/// Python's message for one file, after the context and file label it always starts with.
fn failed(text: &ScanText<'_>, detail: String) -> Stop {
    Stop::Failed(format!(
        "{} '{}' {detail}",
        context_label(text.source),
        text.file
    ))
}

/// Python's message for unclosed text, which names only the context.
fn unclosed(text: &ScanText<'_>, kind: Unclosed) -> Stop {
    let construct = match kind {
        Unclosed::BlockComment => "block comment",
        Unclosed::Quote => "quoted string",
        Unclosed::Parenthesis => "parenthesis",
    };
    Stop::Failed(format!(
        "{} contains an unclosed {construct}",
        context_label(text.source)
    ))
}

fn trailing_ceremonial_select(
    sql: &[u8],
    start: usize,
    text: &ScanText<'_>,
    syntax: &LexicalSyntax,
) -> Scan<bool> {
    let index = skip_ignorable(sql, start, text, syntax)?;
    let Some(select_end) = try_consume_keyword(sql, index, b"SELECT")? else {
        return Ok(false);
    };
    let index = skip_ignorable(sql, select_end, text, syntax)?;
    if sql.get(index) != Some(&b'1') {
        return Ok(false);
    }
    let index = skip_ignorable(sql, index + 1, text, syntax)?;
    trailing_statement_end(sql, index, text, syntax)
}

fn trailing_statement_end(
    sql: &[u8],
    start: usize,
    text: &ScanText<'_>,
    syntax: &LexicalSyntax,
) -> Scan<bool> {
    let mut index = start;
    if sql.get(index) == Some(&b';') {
        index = skip_ignorable(sql, index + 1, text, syntax)?;
    }
    Ok(index == sql.len())
}

fn skip_ignorable(
    sql: &[u8],
    start: usize,
    text: &ScanText<'_>,
    syntax: &LexicalSyntax,
) -> Scan<usize> {
    let mut index = start;
    while let Some(&byte) = sql.get(index) {
        if !byte.is_ascii() {
            return Err(Stop::Deferred);
        }
        if is_python_space(byte) {
            index += 1;
            continue;
        }
        if QUOTE_TOKENS.contains(&byte) {
            return Ok(index);
        }
        match dialect_non_code_end(sql, index, syntax) {
            Ok(Some(end)) => index = end,
            Ok(None) => return Ok(index),
            Err(kind) => return Err(unclosed(text, kind)),
        }
    }
    Ok(index)
}

/// Python's keyword match; text after the first non-ASCII character needs Python's case tables.
fn try_consume_keyword(sql: &[u8], start: usize, keyword: &[u8]) -> Scan<Option<usize>> {
    let end = start + keyword.len();
    let window = &sql[start.min(sql.len())..end.min(sql.len())];
    if let Some(non_ascii) = window.iter().position(|byte| !byte.is_ascii()) {
        return if window[..non_ascii].eq_ignore_ascii_case(&keyword[..non_ascii]) {
            Err(Stop::Deferred)
        } else {
            Ok(None)
        };
    }
    if !window.eq_ignore_ascii_case(keyword) {
        return Ok(None);
    }
    if let Some(&next) = sql.get(end) {
        if !next.is_ascii() {
            return Err(Stop::Deferred);
        }
        if is_identifier_character(next) {
            return Ok(None);
        }
    }
    if let Some(&previous) = start.checked_sub(1).and_then(|index| sql.get(index)) {
        if !previous.is_ascii() {
            return Err(Stop::Deferred);
        }
        if is_identifier_character(previous) {
            return Ok(None);
        }
    }
    Ok(Some(end))
}

fn read_identifier<'sql>(text: &ScanText<'sql>, start: usize) -> Scan<(&'sql str, usize)> {
    let sql = text.sql.as_bytes();
    match sql.get(start) {
        Some(byte) if !byte.is_ascii() => return Err(Stop::Deferred),
        Some(byte) if byte.is_ascii_alphabetic() || *byte == b'_' => {}
        _ => return Err(failed(text, "expected a CTE name".to_owned())),
    }
    let mut index = start + 1;
    while let Some(&byte) = sql.get(index) {
        if !byte.is_ascii() {
            return Err(Stop::Deferred);
        }
        if !is_identifier_character(byte) {
            break;
        }
        index += 1;
    }
    Ok((&text.sql[start..index], index))
}

fn matching_paren(text: &ScanText<'_>, open: usize, syntax: &LexicalSyntax) -> Scan<usize> {
    dialect_matching_paren(text.sql.as_bytes(), open, syntax).map_err(|kind| unclosed(text, kind))
}

fn is_identifier_character(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

/// ASCII characters Python's `str.isspace` accepts, including the information separators.
fn is_python_space(byte: u8) -> bool {
    matches!(byte, b'\t'..=b'\r' | 0x1c..=0x1f | b' ')
}
