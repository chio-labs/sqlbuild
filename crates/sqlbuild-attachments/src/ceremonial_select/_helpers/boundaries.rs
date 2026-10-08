//! Python's code boundary pattern and `WITH` keyword check.

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

/// Whether `WITH` (any case) starts at `first` as a whole word; None for non-ASCII text.
pub(crate) fn starts_with_keyword(sql: &str, first: usize) -> Option<bool> {
    let mut characters = sql[first..].chars();
    let keyword: String = characters.by_ref().take(4).collect();
    if !keyword.is_ascii() {
        return None;
    }
    if !keyword.eq_ignore_ascii_case("WITH") {
        return Some(false);
    }
    match characters.next() {
        None => Some(true),
        Some(next) if !next.is_ascii() => None,
        Some(next) => Some(!(next.is_ascii_alphanumeric() || next == '_')),
    }
}
