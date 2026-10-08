//! Python's `@param(?![A-Za-z0-9_])\s*\(\s*"name"\s*\)` reference pattern.

use sqlbuild_core::text::main::is_python_space::is_python_space;

const TOKEN: &[u8] = b"@param";

/// Python's `_PARAMETER_TOKEN.match` at `index`.
pub(crate) fn parameter_token_at(bytes: &[u8], index: usize) -> bool {
    bytes[index..].starts_with(TOKEN)
        && !bytes
            .get(index + TOKEN.len())
            .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
}

/// The referenced name and the end of the whole reference, or None for a malformed one.
pub(crate) fn reference_at(sql: &str, index: usize) -> Option<(&str, usize)> {
    let mut cursor: usize = skip_spaces(sql, index + TOKEN.len());
    cursor = consume(sql, cursor, b'(')?;
    cursor = skip_spaces(sql, cursor);
    cursor = consume(sql, cursor, b'"')?;
    let bytes: &[u8] = sql.as_bytes();
    let name_start: usize = cursor;
    if !bytes
        .get(cursor)
        .is_some_and(|byte| byte.is_ascii_alphabetic() || *byte == b'_')
    {
        return None;
    }
    while bytes
        .get(cursor)
        .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
    {
        cursor += 1;
    }
    let name_end: usize = cursor;
    cursor = consume(sql, cursor, b'"')?;
    cursor = skip_spaces(sql, cursor);
    cursor = consume(sql, cursor, b')')?;
    Some((&sql[name_start..name_end], cursor))
}

fn skip_spaces(sql: &str, mut index: usize) -> usize {
    while let Some(character) = sql[index..].chars().next() {
        if !is_python_space(character) {
            break;
        }
        index += character.len_utf8();
    }
    index
}

fn consume(sql: &str, index: usize, byte: u8) -> Option<usize> {
    (sql.as_bytes().get(index) == Some(&byte)).then_some(index + 1)
}
