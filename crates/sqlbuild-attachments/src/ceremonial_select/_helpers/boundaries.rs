//! The code boundary pattern and `WITH` keyword check.

use crate::ceremonial_select::constants::WITH_KEYWORD;

/// Python's boundary pattern: parentheses, `/*`, quotes, `$` and the line comment prefixes.
pub(crate) fn next_boundary(bytes: &[u8], start: usize, prefixes: &[String]) -> Option<usize> {
    (start..bytes.len()).find(|index| is_boundary(&bytes[*index..], prefixes))
}

fn is_boundary(rest: &[u8], prefixes: &[String]) -> bool {
    if matches!(rest[0], b'(' | b')' | b'\'' | b'"' | b'`' | b'$') || rest.starts_with(b"/*") {
        return true;
    }
    for prefix in prefixes {
        if rest.starts_with(prefix.as_bytes()) {
            return true;
        }
    }
    false
}

/// Whether `sql[first:first + 4].upper() == "WITH"` and no identifier character follows.
pub(crate) fn starts_with_keyword(sql: &str, first: usize) -> bool {
    let mut characters = sql[first..].chars();
    let keyword: String = characters
        .by_ref()
        .take(WITH_KEYWORD.chars().count())
        .collect();
    keyword.to_uppercase() == WITH_KEYWORD
        && !characters
            .next()
            .is_some_and(|next| next.is_alphanumeric() || next == '_')
}
