//! Python's `find_macro_call_names`: unique top-level macro call names in encounter order.

use sqlbuild_sqltext::sql_scan::main::matching_paren::matching_paren;
use sqlbuild_sqltext::sql_scan::main::non_code_end::non_code_end;
use sqlbuild_sqltext::sql_scan::models::QuotePolicy;

use crate::compiler::models::SqlTestAssemblyDeferral;

/// Declaration calls that expansion substitutes rather than running as macros.
const DECLARATION_CALLS: [&str; 2] = ["enum", "const"];

type Scan<T> = Result<T, SqlTestAssemblyDeferral>;

/// The names Python's scan returns; text it raises on, or classifies by Unicode, is Python's.
pub(crate) fn macro_call_names(sql: &str) -> Scan<Vec<String>> {
    let bytes = sql.as_bytes();
    let mut names: Vec<String> = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        match non_code_end(bytes, index, QuotePolicy::COMPILER) {
            Ok(Some(end)) => {
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(_) => return Err(SqlTestAssemblyDeferral::MacroCallScan),
        }
        if bytes[index] != b'@' || !macro_call_at(bytes, index)? {
            index += 1;
            continue;
        }
        let name_end = identifier_end(bytes, index + 1)?;
        let name = &sql[index + 1..name_end];
        if !names.iter().any(|known| known == name) {
            names.push(name.to_owned());
        }
        let open = space_end(bytes, name_end)?;
        if bytes.get(open) != Some(&b'(') {
            return Err(SqlTestAssemblyDeferral::MacroCallScan);
        }
        index = matching_paren(bytes, open, QuotePolicy::COMPILER)
            .map_err(|_| SqlTestAssemblyDeferral::MacroCallScan)?
            + 1;
    }
    names.retain(|name| !DECLARATION_CALLS.contains(&name.as_str()));
    Ok(names)
}

/// Python's `_is_macro_call_start`, which skips whitespace after each name character.
fn macro_call_at(bytes: &[u8], at: usize) -> Scan<bool> {
    let Some(&first) = bytes.get(at + 1) else {
        return Ok(false);
    };
    if !ascii(first)? || !(first == b'_' || first.is_ascii_alphabetic()) {
        return Ok(false);
    }
    let mut cursor = at + 2;
    while let Some(&byte) = bytes.get(cursor) {
        if !ascii(byte)? || !is_identifier_continue(byte) {
            break;
        }
        cursor = space_end(bytes, cursor + 1)?;
    }
    Ok(bytes.get(cursor) == Some(&b'('))
}

fn identifier_end(bytes: &[u8], start: usize) -> Scan<usize> {
    let mut cursor = start;
    while let Some(&byte) = bytes.get(cursor) {
        if !ascii(byte)? || !is_identifier_continue(byte) {
            break;
        }
        cursor += 1;
    }
    Ok(cursor)
}

/// Python's `str.isspace` skip; a non-ASCII character there is classified by Python.
fn space_end(bytes: &[u8], start: usize) -> Scan<usize> {
    let mut cursor = start;
    while let Some(&byte) = bytes.get(cursor) {
        if !ascii(byte)?
            || !matches!(
                byte,
                b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c | 0x1c..=0x1f
            )
        {
            break;
        }
        cursor += 1;
    }
    Ok(cursor)
}

fn is_identifier_continue(byte: u8) -> bool {
    byte == b'_' || byte.is_ascii_alphanumeric()
}

fn ascii(byte: u8) -> Scan<bool> {
    if byte.is_ascii() {
        Ok(true)
    } else {
        Err(SqlTestAssemblyDeferral::MacroCallScan)
    }
}
