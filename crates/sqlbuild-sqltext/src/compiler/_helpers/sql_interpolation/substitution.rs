//! Conservative native fast path for compile-wide scalar SQL variables.

use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::{QuotePolicy, Unclosed};
use std::collections::HashMap;
use std::ops::Range;

pub(crate) const UNCHANGED: u8 = 0;
pub(crate) const SUBSTITUTED: u8 = 1;
pub(crate) const FALLBACK: u8 = 2;
/// Python raises for an unknown variable, named in the result, unless only Python holds it.
pub(crate) const UNKNOWN_VARIABLE: u8 = 3;
pub(crate) const UNCLOSED_QUOTE: u8 = 4;
pub(crate) const UNCLOSED_BLOCK_COMMENT: u8 = 5;

/// Why substitution stops before the end of the SQL.
enum Stop {
    Fallback,
    UnknownVariable(String),
}

impl Stop {
    fn result(self) -> (u8, Option<String>) {
        match self {
            Self::Fallback => (FALLBACK, None),
            Self::UnknownVariable(name) => (UNKNOWN_VARIABLE, Some(name)),
        }
    }
}

struct SubstitutionState {
    output: Option<String>,
    copy_start: usize,
}

pub(crate) fn substitute_batch(
    sqls: &[String],
    variables: &[(String, String)],
) -> Vec<(u8, Option<String>)> {
    let variables: HashMap<&str, &str> = variables
        .iter()
        .map(|(name, value)| (name.as_str(), value.as_str()))
        .collect();
    sqls.iter()
        .map(|sql| substitute_one(sql, &variables))
        .collect()
}

fn substitute_one(sql: &str, variables: &HashMap<&str, &str>) -> (u8, Option<String>) {
    if !sql.contains("@@") {
        return (UNCHANGED, None);
    }

    let bytes = sql.as_bytes();
    let mut state = SubstitutionState {
        output: None,
        copy_start: 0,
    };
    let mut index = 0;
    while index < bytes.len() {
        let text_end = match python_non_code_end(bytes, index) {
            Ok(Some(end)) => end,
            Ok(None) => index,
            Err(Unclosed::BlockComment) => return (UNCLOSED_BLOCK_COMMENT, None),
            Err(Unclosed::Quote) => return (UNCLOSED_QUOTE, None),
            Err(Unclosed::Parenthesis) => return (FALLBACK, None),
        };
        if text_end > index {
            let comment = bytes[index..].starts_with(b"--") || bytes[index..].starts_with(b"/*");
            if !comment {
                match substitute_quoted_text(sql, index..text_end, variables, state) {
                    Ok(next_state) => state = next_state,
                    Err(stop) => return stop.result(),
                }
            }
            index = text_end;
            continue;
        }
        if bytes[index..].starts_with(b"@@") {
            match substitute_token(sql, index, variables, state) {
                Ok((end, next_state)) => {
                    state = next_state;
                    index = end;
                }
                Err(stop) => return stop.result(),
            }
            continue;
        }
        index += 1;
    }
    match state.output {
        Some(mut rendered) => {
            rendered.push_str(&sql[state.copy_start..]);
            (SUBSTITUTED, Some(rendered))
        }
        None => (UNCHANGED, None),
    }
}

/// Python's comment and quote end at `index`; only `'` and `"` double, so backticks never escape.
fn python_non_code_end(bytes: &[u8], index: usize) -> Result<Option<usize>, Unclosed> {
    if bytes[index] != b'`' {
        return non_code_end(bytes, index, QuotePolicy::COMPILER);
    }
    bytes[index + 1..]
        .iter()
        .position(|byte| *byte == b'`')
        .map(|offset| Some(index + 1 + offset + 1))
        .ok_or(Unclosed::Quote)
}

/// Python's `_interpolate_sql_segment`: substitute every token inside one quoted literal.
fn substitute_quoted_text(
    sql: &str,
    text: Range<usize>,
    variables: &HashMap<&str, &str>,
    mut state: SubstitutionState,
) -> Result<SubstitutionState, Stop> {
    let mut index = text.start;
    while let Some(offset) = sql[index..text.end].find("@@") {
        let (token_end, next_state) = substitute_token(sql, index + offset, variables, state)?;
        if token_end > text.end {
            return Err(Stop::Fallback);
        }
        state = next_state;
        index = token_end;
    }
    Ok(state)
}

fn substitute_token(
    sql: &str,
    start: usize,
    variables: &HashMap<&str, &str>,
    mut state: SubstitutionState,
) -> Result<(usize, SubstitutionState), Stop> {
    let bytes = sql.as_bytes();
    if bytes[start..].starts_with(b"@@@") {
        let name_start = start + 3;
        let end = if bytes
            .get(name_start)
            .copied()
            .is_some_and(is_identifier_start)
        {
            consume_ascii_identifier(bytes, name_start).ok_or(Stop::Fallback)?
        } else {
            name_start
        };
        return Ok((end, state));
    }
    let name_start = start + 2;
    if bytes[name_start..].starts_with(b"ENV:") || bytes[name_start..].starts_with(b"CTX:") {
        return Err(Stop::Fallback);
    }
    if !bytes
        .get(name_start)
        .copied()
        .is_some_and(is_identifier_start)
    {
        return Err(Stop::Fallback);
    }
    let name_end = consume_ascii_identifier(bytes, name_start).ok_or(Stop::Fallback)?;
    let name = &sql[name_start..name_end];
    let value = variables
        .get(name)
        .ok_or_else(|| Stop::UnknownVariable(name.to_owned()))?;
    let rendered = state
        .output
        .get_or_insert_with(|| String::with_capacity(sql.len()));
    rendered.push_str(&sql[state.copy_start..start]);
    rendered.push_str(value);
    state.copy_start = name_end;
    Ok((name_end, state))
}

fn consume_ascii_identifier(bytes: &[u8], start: usize) -> Option<usize> {
    let mut end = start + 1;
    while bytes.get(end).copied().is_some_and(is_identifier_continue) {
        end += 1;
    }
    if bytes.get(end).is_some_and(|value| !value.is_ascii()) {
        return None;
    }
    Some(end)
}

fn is_identifier_start(value: u8) -> bool {
    value.is_ascii_alphabetic() || value == b'_'
}

fn is_identifier_continue(value: u8) -> bool {
    value.is_ascii_alphanumeric() || value == b'_'
}
