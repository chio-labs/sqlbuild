//! Whitespace normalization `argparse` applies before wrapping help text.

/// `_whitespace_matcher.sub(' ', text).strip()`: ASCII whitespace runs become one space.
pub(crate) fn normalize_whitespace(text: &str) -> String {
    let mut normalized: String = String::with_capacity(text.len());
    let mut in_space: bool = false;
    for character in text.chars() {
        if matches!(character, ' ' | '\t' | '\n' | '\r' | '\x0b' | '\x0c') {
            in_space = true;
            continue;
        }
        if in_space && !normalized.is_empty() {
            normalized.push(' ');
        }
        in_space = false;
        normalized.push(character);
    }
    normalized
}
