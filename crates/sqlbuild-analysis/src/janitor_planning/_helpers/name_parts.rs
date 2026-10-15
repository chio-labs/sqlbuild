//! Fixed-width ASCII segments of reserved relation names.

/// The rest of `name` after an ASCII case-insensitive `prefix`.
pub(crate) fn strip_prefix_folded<'a>(name: &'a str, prefix: &str) -> Option<&'a str> {
    let head: &str = name.get(..prefix.len())?;
    head.eq_ignore_ascii_case(prefix)
        .then(|| name.get(prefix.len()..))
        .flatten()
}

/// `width` leading ASCII digits as a number, and the rest of `text`.
pub(crate) fn leading_number(text: &str, width: usize) -> Option<(u32, &str)> {
    let digits: &str = text.get(..width)?;
    if !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    let value: u32 = digits
        .bytes()
        .fold(0, |total, byte| total * 10 + u32::from(byte - b'0'));
    Some((value, text.get(width..)?))
}

/// The rest of `text` after one ASCII case-insensitive `marker` character.
pub(crate) fn after_marker(text: &str, marker: char) -> Option<&str> {
    let mut characters = text.chars();
    characters
        .next()
        .filter(|character| character.eq_ignore_ascii_case(&marker))
        .map(|_| characters.as_str())
}
