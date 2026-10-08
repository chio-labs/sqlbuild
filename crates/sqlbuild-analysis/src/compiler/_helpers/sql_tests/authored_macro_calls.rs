//! Whether macro expansion would expand a call in one unexpanded SQL test body.

use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_sqltext::sql_scan::main::matching_paren::matching_paren;
use sqlbuild_sqltext::sql_scan::main::non_code_end::non_code_end;
use sqlbuild_sqltext::sql_scan::models::QuotePolicy;

/// Declaration calls that expansion substitutes rather than running as macros.
const DECLARATION_CALLS: [&str; 2] = ["enum", "const"];

/// Whether expansion's call scanner finds a macro call; text it cannot scan leaves expansion to fail.
pub(crate) fn calls_macro(sql: &str) -> bool {
    if !sql.contains('@') {
        return false;
    }
    let bytes = sql.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        match non_code_end(bytes, index, QuotePolicy::COMPILER) {
            Ok(Some(end)) => {
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(_) => return false,
        }
        if bytes[index] == b'@'
            && let Some(open) = call_open(sql, index)
        {
            if !DECLARATION_CALLS.contains(&name_at(sql, index + 1)) {
                return true;
            }
            let Ok(close) = matching_paren(bytes, open, QuotePolicy::COMPILER) else {
                return false;
            };
            index = close + 1;
            continue;
        }
        index += char_at(sql, index).map_or(1, char::len_utf8);
    }
    false
}

/// Python `_is_macro_call_start`, which also skips whitespace between name characters.
fn call_open(sql: &str, at: usize) -> Option<usize> {
    let first = char_at(sql, at + 1)?;
    if !(first == '_' || (first.is_alphabetic() && !first.is_numeric())) {
        return None;
    }
    let mut cursor = at + 1 + first.len_utf8();
    while let Some(character) = char_at(sql, cursor) {
        if !is_identifier_continue(character) {
            break;
        }
        cursor = space_end(sql, cursor + character.len_utf8());
    }
    (sql.as_bytes().get(cursor) == Some(&b'(')).then_some(cursor)
}

fn name_at(sql: &str, start: usize) -> &str {
    let mut end = start;
    while let Some(character) = char_at(sql, end) {
        if !is_identifier_continue(character) {
            break;
        }
        end += character.len_utf8();
    }
    &sql[start..end]
}

fn is_identifier_continue(character: char) -> bool {
    character == '_' || character.is_alphanumeric()
}

fn space_end(sql: &str, start: usize) -> usize {
    let mut index = start;
    while let Some(character) = char_at(sql, index) {
        if !is_python_space(character) {
            break;
        }
        index += character.len_utf8();
    }
    index
}

fn char_at(sql: &str, index: usize) -> Option<char> {
    sql.get(index..).and_then(|rest| rest.chars().next())
}
