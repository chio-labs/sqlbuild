//! Shared exact double-quoted reference marker argument parsing.

/// Read a nonempty marker argument and return the unconsumed text.
pub fn quoted_name(text: &str) -> Option<(&str, &str)> {
    let text = text.strip_prefix('"')?;
    let end = text.find('"')?;
    if end == 0 {
        return None;
    }
    Some((&text[..end], &text[end + 1..]))
}
