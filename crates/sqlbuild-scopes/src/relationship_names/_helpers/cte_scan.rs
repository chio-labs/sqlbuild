//! The top-level CTE scan of Python `extract_sql_test_expected_model_names`, reproduced exactly.

use sqlbuild_sqltext::sql_scan::main::dialect_matching_paren::dialect_matching_paren;
use sqlbuild_sqltext::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;
use std::collections::HashSet;

/// Python raises here, or a non-ASCII code character needs Python's `str` classification.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct Deferred;

type Scan<T> = Result<T, Deferred>;

const EXPECTED_PREFIX: &[u8] = b"__expected__";
const QUOTE_TOKENS: &[u8] = b"'\"`$";
/// Python's parenthesis matcher only looks for comments at these characters.
const PAREN_SCAN_SPECIALS: &[u8] = b"-/#'\"`$()";

/// Return the expected-model names of one SQL test or scenario body.
pub(crate) fn expected_names(sql: &[u8], syntax: &LexicalSyntax) -> Scan<Vec<String>> {
    if !syntax.line_comment_prefixes.iter().all(|prefix| {
        prefix.is_ascii()
            && prefix
                .as_bytes()
                .first()
                .is_some_and(|first| PAREN_SCAN_SPECIALS.contains(first))
    }) {
        return Err(Deferred);
    }
    let start = skip_ignorable(sql, 0, syntax)?;
    if try_consume_keyword(sql, start, b"WITH")?.is_none() {
        return Ok(Vec::new());
    }
    let (names, end) = scan_top_level_ctes(sql, syntax)?;
    if !(trailing_statement_end(sql, end, syntax)? || trailing_ceremonial_select(sql, end, syntax)?)
    {
        return Err(Deferred);
    }
    names
        .into_iter()
        .filter_map(|name| name.strip_prefix(EXPECTED_PREFIX).map(<[u8]>::to_vec))
        .map(|model| {
            if model.is_empty() {
                Err(Deferred)
            } else {
                String::from_utf8(model).map_err(|_| Deferred)
            }
        })
        .collect()
}

fn scan_top_level_ctes<'sql>(
    sql: &'sql [u8],
    syntax: &LexicalSyntax,
) -> Scan<(Vec<&'sql [u8]>, usize)> {
    let with_end =
        try_consume_keyword(sql, skip_ignorable(sql, 0, syntax)?, b"WITH")?.ok_or(Deferred)?;
    let mut index = skip_ignorable(sql, with_end, syntax)?;
    if let Some(recursive_end) = try_consume_keyword(sql, index, b"RECURSIVE")? {
        index = skip_ignorable(sql, recursive_end, syntax)?;
    }
    let mut names: Vec<&[u8]> = Vec::new();
    let mut seen: HashSet<&[u8]> = HashSet::new();
    loop {
        let (name, name_end) = read_identifier(sql, index)?;
        if !seen.insert(name) {
            return Err(Deferred);
        }
        names.push(name);
        index = skip_ignorable(sql, name_end, syntax)?;
        if sql.get(index) == Some(&b'(') {
            index = matching_paren(sql, index, syntax)? + 1;
            index = skip_ignorable(sql, index, syntax)?;
        }
        index = try_consume_keyword(sql, index, b"AS")?.ok_or(Deferred)?;
        index = skip_ignorable(sql, index, syntax)?;
        if sql.get(index) != Some(&b'(') {
            return Err(Deferred);
        }
        index = skip_ignorable(sql, matching_paren(sql, index, syntax)? + 1, syntax)?;
        if sql.get(index) == Some(&b',') {
            index = skip_ignorable(sql, index + 1, syntax)?;
            continue;
        }
        return Ok((names, index));
    }
}

fn trailing_ceremonial_select(sql: &[u8], start: usize, syntax: &LexicalSyntax) -> Scan<bool> {
    let index = skip_ignorable(sql, start, syntax)?;
    let Some(select_end) = try_consume_keyword(sql, index, b"SELECT")? else {
        return Ok(false);
    };
    let index = skip_ignorable(sql, select_end, syntax)?;
    if sql.get(index) != Some(&b'1') {
        return Ok(false);
    }
    let index = skip_ignorable(sql, index + 1, syntax)?;
    trailing_statement_end(sql, index, syntax)
}

fn trailing_statement_end(sql: &[u8], start: usize, syntax: &LexicalSyntax) -> Scan<bool> {
    let mut index = start;
    if sql.get(index) == Some(&b';') {
        index = skip_ignorable(sql, index + 1, syntax)?;
    }
    Ok(index == sql.len())
}

fn skip_ignorable(sql: &[u8], start: usize, syntax: &LexicalSyntax) -> Scan<usize> {
    let mut index = start;
    while let Some(&byte) = sql.get(index) {
        if !byte.is_ascii() {
            return Err(Deferred);
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
            Err(_) => return Err(Deferred),
        }
    }
    Ok(index)
}

fn try_consume_keyword(sql: &[u8], start: usize, keyword: &[u8]) -> Scan<Option<usize>> {
    let end = start + keyword.len();
    let window = &sql[start.min(sql.len())..end.min(sql.len())];
    if !window.is_ascii() {
        return Err(Deferred);
    }
    if !window.eq_ignore_ascii_case(keyword) {
        return Ok(None);
    }
    if let Some(&next) = sql.get(end) {
        if !next.is_ascii() {
            return Err(Deferred);
        }
        if is_identifier_character(next) {
            return Ok(None);
        }
    }
    if let Some(&previous) = start.checked_sub(1).and_then(|index| sql.get(index)) {
        if !previous.is_ascii() {
            return Err(Deferred);
        }
        if is_identifier_character(previous) {
            return Ok(None);
        }
    }
    Ok(Some(end))
}

fn read_identifier(sql: &[u8], start: usize) -> Scan<(&[u8], usize)> {
    let first = *sql.get(start).ok_or(Deferred)?;
    if !(first.is_ascii_alphabetic() || first == b'_') {
        return Err(Deferred);
    }
    let mut index = start + 1;
    while let Some(&byte) = sql.get(index) {
        if !byte.is_ascii() {
            return Err(Deferred);
        }
        if !is_identifier_character(byte) {
            break;
        }
        index += 1;
    }
    Ok((&sql[start..index], index))
}

fn matching_paren(sql: &[u8], open: usize, syntax: &LexicalSyntax) -> Scan<usize> {
    dialect_matching_paren(sql, open, syntax).map_err(|_| Deferred)
}

fn is_identifier_character(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

/// ASCII characters Python's `str.isspace` accepts, including the information separators.
fn is_python_space(byte: u8) -> bool {
    matches!(byte, b'\t'..=b'\r' | 0x1c..=0x1f | b' ')
}
