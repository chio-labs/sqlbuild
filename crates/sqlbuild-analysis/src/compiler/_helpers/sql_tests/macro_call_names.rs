//! Python's `find_macro_call_names`: unique top-level macro call names in encounter order.

use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_alnum::is_python_alnum;
use sqlbuild_core::text::main::is_python_alpha::is_python_alpha;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::sql_scan::main::matching_paren::matching_paren;
use sqlbuild_sqltext::sql_scan::main::non_code_end::non_code_end;
use sqlbuild_sqltext::sql_scan::models::{QuotePolicy, Unclosed};

/// Declaration calls that expansion substitutes rather than running as macros.
const DECLARATION_CALLS: [&str; 2] = ["enum", "const"];
const MISSING_PARENTHESIS: &str = "expected opening parenthesis";

/// The names Python's scan returns, or the message of the `CompileInputError` it raises.
pub(crate) fn macro_call_names(sql: &str) -> Result<Vec<String>, String> {
    let python: PythonText = active_python_text();
    let bytes = sql.as_bytes();
    let mut names: Vec<String> = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        if let Some(end) = non_code_end(bytes, index, QuotePolicy::COMPILER).map_err(unclosed)? {
            index = end;
            continue;
        }
        if bytes[index] != b'@' || !macro_call_at(python, sql, index) {
            index += 1;
            continue;
        }
        let name_end = identifier_end(python, sql, index + 1);
        let name = &sql[index + 1..name_end];
        if !names.iter().any(|known| known == name) {
            names.push(name.to_owned());
        }
        let open = space_end(sql, name_end);
        if bytes.get(open) != Some(&b'(') {
            return Err(MISSING_PARENTHESIS.to_owned());
        }
        index = matching_paren(bytes, open, QuotePolicy::COMPILER).map_err(unclosed)? + 1;
    }
    names.retain(|name| !DECLARATION_CALLS.contains(&name.as_str()));
    Ok(names)
}

/// The message of the `CompileInputError` Python's macro scan raises for unclosed text.
fn unclosed(error: Unclosed) -> String {
    let what = match error {
        Unclosed::BlockComment => "block comment",
        Unclosed::Quote => "quoted string",
        Unclosed::Parenthesis => "parenthesis",
    };
    format!("Macro expansion contains an unclosed {what}")
}

/// Python's `_is_macro_call_start`, which skips whitespace after each name character.
fn macro_call_at(python: PythonText, sql: &str, at: usize) -> bool {
    let Some(first) = char_at(sql, at + 1) else {
        return false;
    };
    if !(first == '_' || is_python_alpha(python, first)) {
        return false;
    }
    let mut cursor = at + 1 + first.len_utf8();
    while let Some(character) = char_at(sql, cursor) {
        if !is_identifier_continue(python, character) {
            break;
        }
        cursor = space_end(sql, cursor + character.len_utf8());
    }
    sql.as_bytes().get(cursor) == Some(&b'(')
}

fn identifier_end(python: PythonText, sql: &str, start: usize) -> usize {
    let mut cursor = start;
    while let Some(character) = char_at(sql, cursor) {
        if !is_identifier_continue(python, character) {
            break;
        }
        cursor += character.len_utf8();
    }
    cursor
}

/// Python's `str.isspace` skip.
fn space_end(sql: &str, start: usize) -> usize {
    let mut cursor = start;
    while let Some(character) = char_at(sql, cursor) {
        if !is_python_space(character) {
            break;
        }
        cursor += character.len_utf8();
    }
    cursor
}

fn is_identifier_continue(python: PythonText, character: char) -> bool {
    character == '_' || is_python_alnum(python, character)
}

fn char_at(sql: &str, index: usize) -> Option<char> {
    sql.get(index..).and_then(|rest| rest.chars().next())
}
