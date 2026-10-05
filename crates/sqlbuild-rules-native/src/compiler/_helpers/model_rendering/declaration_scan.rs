//! Native scan for `@enum(...)` and `@const(...)` references, mirroring Python's expansion walk.

use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::QuotePolicy;

const ENUM_PREFIX: &str = "@enum";
const CONSTANT_PREFIX: &str = "@const";

/// Return the byte offset of every declaration reference in expansion order, or `None` for Python.
pub(crate) fn declaration_reference_starts(sql: &str) -> Option<Vec<usize>> {
    let bytes = sql.as_bytes();
    let mut starts: Vec<usize> = Vec::new();
    let mut cursor = 0;
    while cursor < bytes.len() {
        if !sql[cursor..].contains(ENUM_PREFIX) && !sql[cursor..].contains(CONSTANT_PREFIX) {
            break;
        }
        let Some(start) = next_reference_start(bytes, cursor)? else {
            break;
        };
        let end = if bytes[start..].starts_with(ENUM_PREFIX.as_bytes()) {
            enum_reference_end(bytes, start)?
        } else {
            constant_reference_end(bytes, start)?
        };
        starts.push(start);
        cursor = end;
    }
    Some(starts)
}

fn next_reference_start(bytes: &[u8], start: usize) -> Option<Option<usize>> {
    let mut index = start;
    while index < bytes.len() {
        let Some(offset) = bytes[index..]
            .iter()
            .position(|byte| is_scan_special(*byte))
        else {
            return Some(None);
        };
        index += offset;
        match non_code_end(bytes, index, QuotePolicy::COMPILER) {
            Ok(Some(end)) => {
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(_) => return None,
        }
        if bytes[index] == b'@' && reference_kind_matches(bytes, index)? {
            return Some(Some(index));
        }
        index += 1;
    }
    Some(None)
}

fn reference_kind_matches(bytes: &[u8], index: usize) -> Option<bool> {
    for prefix in [ENUM_PREFIX.as_bytes(), CONSTANT_PREFIX.as_bytes()] {
        if bytes[index..].starts_with(prefix) {
            return word_boundary_after(bytes, index + prefix.len());
        }
    }
    Some(false)
}

fn word_boundary_after(bytes: &[u8], index: usize) -> Option<bool> {
    match bytes.get(index) {
        None => Some(true),
        Some(byte) if !byte.is_ascii() => None,
        Some(byte) => Some(!(byte.is_ascii_alphanumeric() || *byte == b'_')),
    }
}

fn enum_reference_end(bytes: &[u8], start: usize) -> Option<usize> {
    let name_end = quoted_name_call_end(bytes, start + ENUM_PREFIX.len())?;
    let dot = whitespace_end(bytes, name_end)?;
    if bytes.get(dot) != Some(&b'.') {
        return None;
    }
    let member_start = whitespace_end(bytes, dot + 1)?;
    identifier_end(bytes, member_start)
}

fn constant_reference_end(bytes: &[u8], start: usize) -> Option<usize> {
    quoted_name_call_end(bytes, start + CONSTANT_PREFIX.len())
}

/// Match `\s*\(\s*(['"])NAME\1\s*\)` and return the offset after the closing parenthesis.
fn quoted_name_call_end(bytes: &[u8], start: usize) -> Option<usize> {
    let open = whitespace_end(bytes, start)?;
    if bytes.get(open) != Some(&b'(') {
        return None;
    }
    let quote_index = whitespace_end(bytes, open + 1)?;
    let quote = *bytes.get(quote_index)?;
    if !matches!(quote, b'\'' | b'"') {
        return None;
    }
    let name_end = identifier_end(bytes, quote_index + 1)?;
    if bytes.get(name_end) != Some(&quote) {
        return None;
    }
    let close = whitespace_end(bytes, name_end + 1)?;
    if bytes.get(close) != Some(&b')') {
        return None;
    }
    Some(close + 1)
}

fn identifier_end(bytes: &[u8], start: usize) -> Option<usize> {
    let first = *bytes.get(start)?;
    if !(first.is_ascii_alphabetic() || first == b'_') {
        return None;
    }
    let mut end = start + 1;
    while bytes
        .get(end)
        .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
    {
        end += 1;
    }
    Some(end)
}

/// Skip Python `\s*`; a non-ASCII character could be Unicode whitespace, so Python decides.
fn whitespace_end(bytes: &[u8], start: usize) -> Option<usize> {
    let mut end = start;
    while let Some(byte) = bytes.get(end) {
        if !byte.is_ascii() {
            return None;
        }
        if !is_python_ascii_whitespace(*byte) {
            break;
        }
        end += 1;
    }
    Some(end)
}

fn is_python_ascii_whitespace(byte: u8) -> bool {
    matches!(byte, b'\t'..=b'\r' | 0x1c..=0x1f | b' ')
}

fn is_scan_special(byte: u8) -> bool {
    matches!(byte, b'\'' | b'"' | b'`' | b'$' | b'@' | b'/' | b'-')
}
