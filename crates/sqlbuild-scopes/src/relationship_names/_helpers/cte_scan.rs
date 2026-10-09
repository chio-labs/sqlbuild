//! The top-level CTE scan of `extract_top_level_ctes_with_scanner`.

use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_sqltext::sql_scan::main::dialect_matching_paren::dialect_matching_paren;
use sqlbuild_sqltext::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use sqlbuild_sqltext::sql_scan::models::{LexicalSyntax, Unclosed};
use std::collections::HashSet;

use crate::relationship_names::models::RelationshipSource;

/// The message the scan raises.
pub(crate) type Stop = String;

type Scan<T> = Result<T, Stop>;

const EXPECTED_PREFIX: &str = "__expected__";
const QUOTE_TOKENS: &[u8] = b"'\"`$";

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
    if try_consume_keyword(text.sql, start, "WITH").is_none() {
        return Ok(Vec::new());
    }
    let ctes = top_level_ctes(text, syntax)?;
    ctes.into_iter()
        .filter_map(|(name, _)| name.strip_prefix(EXPECTED_PREFIX).map(str::to_owned))
        .map(|model| {
            if model.is_empty() {
                Err(format!(
                    "{} '{}' must use __expected__<model> to identify a target",
                    context_label(text.source),
                    text.file
                ))
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
    let sql = text.sql.as_bytes();
    let with_end = try_consume_keyword(text.sql, skip_ignorable(sql, 0, text, syntax)?, "WITH")
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
    if let Some(recursive_end) = try_consume_keyword(text.sql, index, "RECURSIVE") {
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
        index = try_consume_keyword(text.sql, index, "AS")
            .ok_or_else(|| failed(text, "expected keyword AS".to_owned()))?;
        index = skip_ignorable(sql, index, text, syntax)?;
        if let Some(hint) = materialization_hint(sql, index, text, syntax)? {
            return Err(failed(
                text,
                format!(
                    "CTE '{name}' must not use AS {hint}; materialization hints are not supported \
                     in {} CTEs",
                    context_label(text.source)
                ),
            ));
        }
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

/// The `MATERIALIZED` or `NOT MATERIALIZED` hint after a CTE's `AS`, if any.
fn materialization_hint(
    sql: &[u8],
    start: usize,
    text: &ScanText<'_>,
    syntax: &LexicalSyntax,
) -> Scan<Option<&'static str>> {
    if try_consume_keyword(text.sql, start, "MATERIALIZED").is_some() {
        return Ok(Some("MATERIALIZED"));
    }
    let Some(not_end) = try_consume_keyword(text.sql, start, "NOT") else {
        return Ok(None);
    };
    let index = skip_ignorable(sql, not_end, text, syntax)?;
    Ok(try_consume_keyword(text.sql, index, "MATERIALIZED").map(|_| "NOT MATERIALIZED"))
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
    format!("{} '{}' {detail}", context_label(text.source), text.file)
}

/// Python's message for unclosed text, which names only the context.
fn unclosed(text: &ScanText<'_>, kind: Unclosed) -> Stop {
    let construct = match kind {
        Unclosed::BlockComment => "block comment",
        Unclosed::Quote => "quoted string",
        Unclosed::Parenthesis => "parenthesis",
    };
    format!(
        "{} contains an unclosed {construct}",
        context_label(text.source)
    )
}

fn trailing_ceremonial_select(
    sql: &[u8],
    start: usize,
    text: &ScanText<'_>,
    syntax: &LexicalSyntax,
) -> Scan<bool> {
    let index = skip_ignorable(sql, start, text, syntax)?;
    let Some(select_end) = try_consume_keyword(text.sql, index, "SELECT") else {
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
    while let Some(character) = text.sql[index..].chars().next() {
        if is_python_space(character) {
            index += character.len_utf8();
            continue;
        }
        if QUOTE_TOKENS.contains(&sql[index]) {
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

/// `sql[start:start + len(keyword)].upper() == keyword` between non-identifier characters.
fn try_consume_keyword(sql: &str, start: usize, keyword: &str) -> Option<usize> {
    let window_end: usize = sql[start..]
        .char_indices()
        .nth(keyword.len())
        .map_or(sql.len(), |(offset, _)| start + offset);
    if sql[start..window_end].to_uppercase() != keyword {
        return None;
    }
    let continues = |character: Option<char>| character.is_some_and(is_identifier_character);
    if continues(sql[window_end..].chars().next()) || continues(sql[..start].chars().next_back()) {
        return None;
    }
    Some(window_end)
}

fn read_identifier<'sql>(text: &ScanText<'sql>, start: usize) -> Scan<(&'sql str, usize)> {
    let mut characters = text.sql[start..].char_indices();
    match characters.next() {
        Some((_, first)) if first.is_alphabetic() || first == '_' => {}
        _ => return Err(failed(text, "expected a CTE name".to_owned())),
    }
    let end: usize = characters
        .find(|(_, character)| !is_identifier_character(*character))
        .map_or(text.sql.len(), |(offset, _)| start + offset);
    Ok((&text.sql[start..end], end))
}

fn matching_paren(text: &ScanText<'_>, open: usize, syntax: &LexicalSyntax) -> Scan<usize> {
    dialect_matching_paren(text.sql.as_bytes(), open, syntax).map_err(|kind| unclosed(text, kind))
}

/// Python's `isalnum() or _`.
fn is_identifier_character(character: char) -> bool {
    character.is_alphanumeric() || character == '_'
}
