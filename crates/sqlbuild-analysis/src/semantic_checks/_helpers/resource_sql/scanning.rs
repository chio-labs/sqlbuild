//! Python `re` building blocks over code points: `\s`, `\w`, `\b` and ignore-case words.

use sqlbuild_core::text::main::is_word_char::is_word_char;

/// Python's `\w` for the character at `index`, false past either end.
pub(crate) fn word_at(text: &[char], index: Option<usize>) -> bool {
    index
        .and_then(|index| text.get(index))
        .is_some_and(|character| is_word_char(*character))
}

/// Python's `\b` before `index`, where the next character is a word character.
pub(crate) fn starts_word(text: &[char], index: usize) -> bool {
    !word_at(text, index.checked_sub(1))
}

/// The end of `\s*` (or `\s+` when `required`) from `index`.
pub(crate) fn spaces(text: &[char], index: usize, required: bool) -> Option<usize> {
    let end = index
        + text[index.min(text.len())..]
            .iter()
            .take_while(|character| char::is_whitespace(**character))
            .count();
    (!required || end > index).then_some(end)
}

/// The end of `\w+` from `index`.
pub(crate) fn words(text: &[char], index: usize) -> Option<usize> {
    let mut end = index;
    while word_at(text, Some(end)) {
        end += 1;
    }
    (end > index).then_some(end)
}

/// The end of the ASCII `literal` at `index`, matched under `re.IGNORECASE` when `ignore_case`.
pub(crate) fn literal(
    text: &[char],
    index: usize,
    literal: &str,
    ignore_case: bool,
) -> Option<usize> {
    let mut end = index;
    for expected in literal.chars() {
        let actual = *text.get(end)?;
        let matched = if ignore_case && expected.is_ascii_alphabetic() {
            actual.eq_ignore_ascii_case(&expected)
        } else {
            actual == expected
        };
        if !matched {
            return None;
        }
        end += 1;
    }
    Some(end)
}

/// The text of `text[start..end]`.
pub(crate) fn slice(text: &[char], start: usize, end: usize) -> String {
    text[start..end].iter().collect()
}
