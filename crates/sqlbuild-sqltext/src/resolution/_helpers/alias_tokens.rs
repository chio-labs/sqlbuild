//! Alias token reading shared by source normalization.

pub(crate) fn skip_space(sql: &str, start: usize) -> usize {
    start + sql.get(start..).unwrap_or_default().len()
        - sql.get(start..).unwrap_or_default().trim_start().len()
}

pub(crate) fn alias_token(sql: &str, start: usize) -> Option<(usize, &str)> {
    let suffix = sql.get(start..)?;
    let first = suffix.chars().next()?;
    if matches!(first, '[' | '"' | '`') {
        let close = if first == '[' { ']' } else { first };
        let end = start + 1 + suffix[1..].find(close)? + 1;
        return Some((end, &sql[start..end]));
    }
    if !(first.is_ascii_alphabetic() || first == '_') {
        return None;
    }
    let length = suffix
        .bytes()
        .take_while(|c| c.is_ascii_alphanumeric() || matches!(c, b'_' | b'$'))
        .count();
    Some((start + length, &suffix[..length]))
}
