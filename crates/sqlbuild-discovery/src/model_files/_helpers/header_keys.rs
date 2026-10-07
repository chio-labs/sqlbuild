//! Python's `reject_unsupported_header_keys`: the message, its line and the key suggestions.

use crate::_helpers::suggestions::unsupported_keys_help;
use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::is_python_word::is_python_word;

/// The facts of one header that declares keys outside its supported set.
pub(crate) struct UnsupportedKeys<'a> {
    pub(crate) statement: &'a str,
    pub(crate) file_path: &'a str,
    pub(crate) header: &'a str,
    /// One-based line of the header start.
    pub(crate) header_line: usize,
    pub(crate) keys: &'a [&'a str],
    pub(crate) supported_keys: &'a [String],
}

pub(crate) fn unsupported_keys_failure(facts: &UnsupportedKeys<'_>) -> DiscoveryFailure {
    let UnsupportedKeys {
        statement,
        file_path,
        header,
        header_line,
        keys,
        supported_keys,
    } = facts;
    let header_chars: Vec<char> = header.chars().collect();
    let key_offset: usize = header_key_offset(&header_chars, keys[0]);
    let line: usize = header_line
        + header_chars[..key_offset]
            .iter()
            .filter(|character| **character == '\n')
            .count();
    DiscoveryFailure {
        kind: FailureKind::ModelSql,
        message: format!(
            "{statement} in '{file_path}:{line}' has unsupported keys: {}",
            keys.join(", ")
        ),
        help: Some(unsupported_keys_help(keys, supported_keys)),
    }
}

/// `re.search(r"(?:^|[(,])(?:\s|--[^\n]*(?:\n|$)|/\*.*?\*/)*(KEY)\b", header, re.S).start(1)`.
fn header_key_offset(header: &[char], key: &str) -> usize {
    let key: Vec<char> = key.chars().collect();
    let length: usize = header.len();
    let mut found: Vec<Option<usize>> = vec![None; length + 1];
    for position in (0..=length).rev() {
        found[position] = skip_then_key(header, &key, position, &found);
    }
    for start in 0..=length {
        if start == 0
            && let Some(offset) = found[0]
        {
            return offset;
        }
        if start < length
            && matches!(header[start], '(' | ',')
            && let Some(offset) = found[start + 1]
        {
            return offset;
        }
    }
    0
}

/// Where the key starts when the skip loop is entered at `position`, in backtracking order.
fn skip_then_key(
    header: &[char],
    key: &[char],
    position: usize,
    found: &[Option<usize>],
) -> Option<usize> {
    let length = header.len();
    if position < length {
        if is_python_space(header[position])
            && let Some(offset) = found[position + 1]
        {
            return Some(offset);
        }
        if header[position..].starts_with(&['-', '-']) {
            let end = header[position + 2..]
                .iter()
                .position(|character| *character == '\n')
                .map_or(length, |offset| position + 2 + offset + 1);
            if let Some(offset) = found[end] {
                return Some(offset);
            }
        }
        if header[position..].starts_with(&['/', '*']) {
            let mut close = position + 2;
            while close + 1 < length {
                if header[close] == '*'
                    && header[close + 1] == '/'
                    && let Some(offset) = found[close + 2]
                {
                    return Some(offset);
                }
                close += 1;
            }
        }
    }
    let end = position + key.len();
    if header.get(position..end) == Some(key) && word_boundary(header, end) {
        return Some(position);
    }
    None
}

/// `\b` at `position`: exactly one side is a word character.
fn word_boundary(text: &[char], position: usize) -> bool {
    let before = position
        .checked_sub(1)
        .and_then(|index| text.get(index))
        .is_some_and(|character| is_python_word(*character));
    let after = text
        .get(position)
        .is_some_and(|character| is_python_word(*character));
    before != after
}
