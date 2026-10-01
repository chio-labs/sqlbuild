//! Split a leading top-level WITH into authored CTE and body slices without reparsing.

use std::collections::HashSet;

use crate::compiler::_helpers::sql_tests::cte_sql::keyword_end;
use crate::rules::main::quote_policy::quote_policy;
use crate::sql_scan::main::comment_end::comment_end;
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::main::skip_whitespace::skip_whitespace;
use crate::sql_scan::models::{QuotePolicy, Unclosed};

/// Dialect lexical rules for slicing authored SQL.
#[derive(Clone, Copy, Debug)]
pub(crate) struct SliceDialect {
    policy: QuotePolicy,
    bracket_identifiers: bool,
}

impl SliceDialect {
    /// Lexical rules for a SQL-analysis dialect name; dollar-quoted text is always opaque.
    pub(crate) fn new(dialect_name: Option<&str>) -> Self {
        let name = dialect_name.unwrap_or("generic");
        Self {
            policy: QuotePolicy {
                dollar_quotes: true,
                ..quote_policy(name)
            },
            bracket_identifiers: is_tsql(name),
        }
    }

    /// Whether the dialect rejects a WITH clause nested inside a CTE body.
    pub(crate) fn rejects_nested_with(self) -> bool {
        self.bracket_identifiers
    }
}

/// One authored CTE: its header (name plus optional column list) and parenthesised body.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct CteSlice<'a> {
    pub(crate) header_start: usize,
    pub(crate) header: &'a str,
    pub(crate) key: String,
    pub(crate) body: &'a str,
}

/// The CTEs of a leading top-level WITH and the statement body that follows them.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct WithSlices<'a> {
    pub(crate) ctes: Vec<CteSlice<'a>>,
    pub(crate) body: &'a str,
}

/// Authored slices of a leading WITH; `None` when absent or not liftable verbatim.
pub(crate) fn split_top_level_with(
    sql: &str,
    dialect: SliceDialect,
) -> Result<Option<WithSlices<'_>>, Unclosed> {
    let mut index = skip_ignorable(sql, 0)?;
    let Some(with_end) = keyword_end(sql, index, "WITH") else {
        return Ok(None);
    };
    index = skip_ignorable(sql, with_end)?;
    if keyword_end(sql, index, "RECURSIVE").is_some() {
        return Ok(None);
    }
    let mut ctes: Vec<CteSlice<'_>> = Vec::new();
    loop {
        let Some((key, name_end)) = read_identifier(sql, index, dialect)? else {
            return Ok(None);
        };
        let mut header_end = name_end;
        let mut cursor = skip_ignorable(sql, name_end)?;
        if sql.as_bytes().get(cursor) == Some(&b'(') {
            header_end = matching_paren(sql, cursor, dialect)? + 1;
            cursor = skip_ignorable(sql, header_end)?;
        }
        let Some(as_end) = keyword_end(sql, cursor, "AS") else {
            return Ok(None);
        };
        cursor = skip_ignorable(sql, as_end)?;
        if sql.as_bytes().get(cursor) != Some(&b'(') {
            return Ok(None);
        }
        let close = matching_paren(sql, cursor, dialect)?;
        ctes.push(CteSlice {
            header_start: index,
            header: &sql[index..header_end],
            key,
            body: &sql[cursor + 1..close],
        });
        let next = skip_ignorable(sql, close + 1)?;
        if sql.as_bytes().get(next) == Some(&b',') {
            index = skip_ignorable(sql, next + 1)?;
            continue;
        }
        let body = strip_statement_terminators(&sql[skip_whitespace(sql, close + 1)..], dialect);
        if body.is_empty() || matches!(sql.as_bytes().get(next), Some(b')' | b';') | None) {
            return Ok(None);
        }
        return Ok(Some(WithSlices { ctes, body }));
    }
}

/// Mark the CTEs the statement body reads, directly or through other CTEs.
pub(crate) fn used_ctes(split: &WithSlices<'_>, dialect: SliceDialect) -> Vec<bool> {
    let mut referenced = identifier_keys(split.body, dialect);
    let mut used = vec![false; split.ctes.len()];
    for (index, cte) in split.ctes.iter().enumerate().rev() {
        if referenced.contains(&cte.key) {
            used[index] = true;
            referenced.extend(identifier_keys(cte.body, dialect));
        }
    }
    used
}

/// Case-folded identifiers of code outside comments and string literals, quoted ones unquoted.
pub(crate) fn identifier_keys(sql: &str, dialect: SliceDialect) -> HashSet<String> {
    let bytes = sql.as_bytes();
    let mut keys: HashSet<String> = HashSet::new();
    let mut index = 0;
    while index < bytes.len() {
        match read_identifier(sql, index, dialect) {
            Ok(Some((key, end))) => {
                keys.insert(key);
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(_) => return keys,
        }
        match opaque_end(bytes, index, dialect) {
            Ok(Some(end)) => index = end,
            Ok(None) => index += sql[index..].chars().next().map_or(1, char::len_utf8),
            Err(_) => return keys,
        }
    }
    keys
}

fn is_tsql(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        "tsql" | "mssql" | "sqlserver" | "fabric"
    )
}

/// Drop trailing `;` terminators and the whitespace or comments after them.
pub(crate) fn strip_statement_terminators(sql: &str, dialect: SliceDialect) -> &str {
    let bytes = sql.as_bytes();
    let mut code_end = 0;
    let mut terminated = false;
    let mut index = 0;
    while index < bytes.len() {
        match comment_end(bytes, index) {
            Ok(Some(end)) => {
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(_) => return sql.trim_end(),
        }
        let next = match opaque_end(bytes, index, dialect) {
            Ok(Some(end)) => end,
            Ok(None) => index + sql[index..].chars().next().map_or(1, char::len_utf8),
            Err(_) => return sql.trim_end(),
        };
        match bytes[index] {
            b';' => terminated = true,
            byte if byte.is_ascii_whitespace() => {}
            _ => {
                code_end = next;
                terminated = false;
            }
        }
        index = next;
    }
    if terminated {
        sql[..code_end].trim_end()
    } else {
        sql.trim_end()
    }
}

/// Read the identifier at `start`, returning its case-folded key and end offset.
pub(crate) fn read_identifier(
    sql: &str,
    start: usize,
    dialect: SliceDialect,
) -> Result<Option<(String, usize)>, Unclosed> {
    let bytes = sql.as_bytes();
    let Some(&opening) = bytes.get(start) else {
        return Ok(None);
    };
    if opening == b'[' && dialect.bracket_identifiers {
        let end = bracket_end(bytes, start)?;
        let name = sql[start + 1..end - 1].replace("]]", "]");
        return Ok(Some((name.to_lowercase(), end)));
    }
    if dialect.policy.is_quote(opening) && opening != b'\'' {
        let Some(end) = non_code_end(bytes, start, dialect.policy)? else {
            return Ok(None);
        };
        let quote = char::from(opening).to_string();
        let name = sql[start + 1..end - 1].replace(&quote.repeat(2), &quote);
        return Ok(Some((name.to_lowercase(), end)));
    }
    let Some(first) = sql[start..].chars().next() else {
        return Ok(None);
    };
    if !(first == '_' || first.is_alphabetic()) {
        return Ok(None);
    }
    let end = sql[start..]
        .char_indices()
        .find(|(_, character)| !is_identifier_continue(*character))
        .map_or(sql.len(), |(offset, _)| start + offset);
    Ok(Some((sql[start..end].to_lowercase(), end)))
}

fn is_identifier_continue(character: char) -> bool {
    character == '_' || character == '$' || character.is_alphanumeric()
}

fn skip_ignorable(sql: &str, mut index: usize) -> Result<usize, Unclosed> {
    loop {
        index = skip_whitespace(sql, index);
        match comment_end(sql.as_bytes(), index)? {
            Some(end) => index = end,
            None => return Ok(index),
        }
    }
}

fn matching_paren(sql: &str, open: usize, dialect: SliceDialect) -> Result<usize, Unclosed> {
    let bytes = sql.as_bytes();
    let mut depth = 0usize;
    let mut index = open;
    while index < bytes.len() {
        if let Some(end) = opaque_end(bytes, index, dialect)? {
            index = end;
            continue;
        }
        match bytes[index] {
            b'(' => depth += 1,
            b')' => {
                depth = depth.saturating_sub(1);
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => {}
        }
        index += 1;
    }
    Err(Unclosed::Parenthesis)
}

/// Return the end of the comment, string or quoted identifier at `index`, if one starts there.
pub(crate) fn opaque_end(
    bytes: &[u8],
    index: usize,
    dialect: SliceDialect,
) -> Result<Option<usize>, Unclosed> {
    if dialect.bracket_identifiers && bytes[index] == b'[' {
        return bracket_end(bytes, index).map(Some);
    }
    non_code_end(bytes, index, dialect.policy)
}

fn bracket_end(bytes: &[u8], start: usize) -> Result<usize, Unclosed> {
    let mut index = start + 1;
    while index < bytes.len() {
        if bytes[index] == b']' {
            if bytes.get(index + 1) == Some(&b']') {
                index += 2;
                continue;
            }
            return Ok(index + 1);
        }
        index += 1;
    }
    Err(Unclosed::Quote)
}
