//! Python string operations over character slices, indexed as Python indexes `str`.

use sqlbuild_core::text::main::python_isalnum::python_isalnum;
use sqlbuild_core::text::main::python_isspace::python_isspace;

/// `text[start:end]` with Python's clamping; an inverted range is empty.
pub(crate) fn slice(text: &[char], start: usize, end: usize) -> &[char] {
    let end: usize = end.min(text.len());
    if start >= end {
        return &[];
    }
    &text[start..end]
}

/// `text[start:]` with Python's clamping.
pub(crate) fn tail(text: &[char], start: usize) -> &[char] {
    slice(text, start, text.len())
}

pub(crate) fn strip(text: &[char]) -> &[char] {
    rstrip(lstrip(text))
}

pub(crate) fn lstrip(text: &[char]) -> &[char] {
    let start: usize = text
        .iter()
        .position(|character| !python_isspace(*character))
        .unwrap_or(text.len());
    &text[start..]
}

pub(crate) fn rstrip(text: &[char]) -> &[char] {
    let end: usize = text
        .iter()
        .rposition(|character| !python_isspace(*character))
        .map_or(0, |index| index + 1);
    &text[..end]
}

/// `str.isalpha` for one character: alphanumeric without being a number.
pub(crate) fn is_alpha(character: char) -> bool {
    python_isalnum(character) && !character.is_numeric()
}

/// Python's `\w` for one character.
pub(crate) fn is_word(character: char) -> bool {
    character == '_' || python_isalnum(character)
}

/// `text.find(needle, start)`.
pub(crate) fn find(text: &[char], needle: &[char], start: usize) -> Option<usize> {
    if needle.is_empty() {
        return (start <= text.len()).then_some(start);
    }
    (start..text.len().saturating_sub(needle.len() - 1))
        .find(|index| text[*index..].starts_with(needle))
}

/// `text.rfind(character, 0, end)`.
pub(crate) fn rfind_before(text: &[char], character: char, end: usize) -> Option<usize> {
    slice(text, 0, end)
        .iter()
        .rposition(|found| *found == character)
}

pub(crate) fn contains(text: &[char], needle: &str) -> bool {
    let needle: Vec<char> = needle.chars().collect();
    find(text, &needle, 0).is_some()
}

pub(crate) fn line_count(text: &[char]) -> usize {
    text.iter().filter(|character| **character == '\n').count() + 1
}

/// The offset where each line of `text` starts.
pub(crate) fn line_starts(text: &[char]) -> Vec<usize> {
    let mut starts: Vec<usize> = vec![0];
    starts.extend(
        text.iter()
            .enumerate()
            .filter(|(_, character)| **character == '\n')
            .map(|(index, _)| index + 1),
    );
    starts
}

/// The one-based line and column of `offset`.
pub(crate) fn position(offset: usize, starts: &[usize]) -> (usize, usize) {
    let line_index: usize = starts.partition_point(|start| *start <= offset) - 1;
    (line_index + 1, offset - starts[line_index] + 1)
}

pub(crate) fn chars(text: &str) -> Vec<char> {
    text.chars().collect()
}

pub(crate) fn string(text: &[char]) -> String {
    text.iter().collect()
}
