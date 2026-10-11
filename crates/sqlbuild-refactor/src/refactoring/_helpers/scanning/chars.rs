//! Code-point text operations with Python `str` semantics.

/// The code points of a text, so offsets match Python string offsets.
pub(crate) fn chars(text: &str) -> Vec<char> {
    text.chars().collect()
}

/// `text[start:end]` with Python's clamping.
pub(crate) fn slice(text: &[char], start: usize, end: usize) -> String {
    let end = end.min(text.len());
    let start = start.min(end);
    text[start..end].iter().collect()
}

/// `text.startswith(needle, at)`.
pub(crate) fn starts_with(text: &[char], at: usize, needle: &str) -> bool {
    (at..)
        .zip(needle.chars())
        .all(|(index, character)| text.get(index) == Some(&character))
}

/// `text.find(needle, from)`.
pub(crate) fn find(text: &[char], needle: &str, from: usize) -> Option<usize> {
    let length = needle.chars().count();
    if length == 0 {
        return (from <= text.len()).then_some(from);
    }
    (from..=text.len().saturating_sub(length)).find(|index| starts_with(text, *index, needle))
}

/// `text.rfind(needle, start, end)` for a non-empty needle.
pub(crate) fn rfind(text: &[char], needle: &str, start: usize, end: usize) -> Option<usize> {
    let length = needle.chars().count();
    let end = end.min(text.len());
    if end < start + length {
        return None;
    }
    (start..=end - length)
        .rev()
        .find(|index| starts_with(text, *index, needle))
}

/// `text.count(needle, 0, end)` for a one-character needle.
pub(crate) fn count_before(text: &[char], needle: char, end: usize) -> usize {
    text[..end.min(text.len())]
        .iter()
        .filter(|character| **character == needle)
        .count()
}

/// Whether two characters match under `re.IGNORECASE`.
pub(crate) fn same_ignoring_case(left: char, right: char) -> bool {
    left == right || left.to_lowercase().eq(right.to_lowercase())
}

/// Whether `needle` occurs at `at`, ignoring case per character as `re.IGNORECASE` does.
pub(crate) fn starts_with_ignoring_case(text: &[char], at: usize, needle: &[char]) -> bool {
    needle.iter().enumerate().all(|(offset, character)| {
        text.get(at + offset)
            .is_some_and(|found| same_ignoring_case(*found, *character))
    })
}

/// `[A-Za-z0-9_$]`, the identifier characters of refactoring patterns.
pub(crate) fn is_identifier_character(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '_' | '$')
}
