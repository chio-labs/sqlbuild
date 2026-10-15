//! Anchored matching primitives with Python `re` whitespace and word-boundary semantics.

use sqlbuild_core::text::main::python_isalnum::python_isalnum;
use sqlbuild_core::text::main::python_isspace::python_isspace;

/// Python's `\w`: alphanumeric or `_`.
fn is_word(character: char) -> bool {
    character == '_' || python_isalnum(character)
}

/// The position after any whitespace at `position` (`\s*+`).
pub(crate) fn skip_whitespace(text: &str, position: usize) -> usize {
    let rest: &str = &text[position..];
    position + (rest.len() - rest.trim_start_matches(python_isspace).len())
}

/// The position after at least one whitespace character at `position` (`\s++`).
pub(crate) fn whitespace(text: &str, position: usize) -> Option<usize> {
    let end: usize = skip_whitespace(text, position);
    (end > position).then_some(end)
}

/// Whether only whitespace remains from `position` (`\s*+$`).
pub(crate) fn only_whitespace(text: &str, position: usize) -> bool {
    skip_whitespace(text, position) == text.len()
}

/// Whether `position` is a word boundary (`\b`).
pub(crate) fn word_boundary(text: &str, position: usize) -> bool {
    let before: bool = text[..position].chars().next_back().is_some_and(is_word);
    let after: bool = text[position..].chars().next().is_some_and(is_word);
    before != after
}

/// The position after an ASCII case-insensitive `word` at `position`.
pub(crate) fn word(text: &str, position: usize, word: &str) -> Option<usize> {
    let end: usize = position + word.len();
    text.as_bytes()
        .get(position..end)
        .filter(|candidate| candidate.eq_ignore_ascii_case(word.as_bytes()))
        .map(|_| end)
}

/// The position after `words` separated by whitespace (`A\s++B`).
pub(crate) fn phrase(text: &str, position: usize, words: &[&str]) -> Option<usize> {
    let mut end: usize = position;
    for (index, expected) in words.iter().enumerate() {
        if index > 0 {
            end = whitespace(text, end)?;
        }
        end = word(text, end, expected)?;
    }
    Some(end)
}

/// The position after the first of `phrases` that matches and is followed by whitespace.
pub(crate) fn phrase_then_whitespace(
    text: &str,
    position: usize,
    phrases: &[&[&str]],
) -> Option<usize> {
    phrases
        .iter()
        .find_map(|words| whitespace(text, phrase(text, position, words)?))
}

/// The position after `words` when it ends at a word boundary (`A\b`).
fn bounded_words(text: &str, position: usize, words: &[&str]) -> Option<usize> {
    phrase(text, position, words).filter(|end| word_boundary(text, *end))
}

/// The position after the first of `phrases` that ends at a word boundary (`(?:A|B)\b`).
pub(crate) fn bounded_phrase(text: &str, position: usize, phrases: &[&[&str]]) -> Option<usize> {
    phrases
        .iter()
        .find_map(|words| bounded_words(text, position, words))
}

/// The position after any repetitions of `phrases`, each followed by whitespace (`(?:..\s++)*+`).
pub(crate) fn repeated_modifiers(text: &str, position: usize, phrases: &[&[&str]]) -> usize {
    let mut end: usize = position;
    while let Some(next) = phrase_then_whitespace(text, end, phrases) {
        end = next;
    }
    end
}
