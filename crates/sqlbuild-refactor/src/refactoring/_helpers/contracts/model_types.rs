//! MODEL header column types: rendering, matching and the authored span of a declared type.

use sqlbuild_sqltext::header_strings::constants::TRIPLE_QUOTE_LENGTH;
use sqlbuild_sqltext::header_strings::main::header_quoted_end::header_quoted_end;
use sqlbuild_sqltext::header_strings::main::opens_triple_quote::opens_triple_quote;

use crate::refactoring::_helpers::scanning::chars::slice;
use crate::refactoring::constants::{
    CONTRACT_CLOSERS, CONTRACT_HEADER_WORD_EXTRA, CONTRACT_OPENERS, CONTRACT_QUOTES,
    CONTRACT_TYPE_KEY,
};

fn is_type_name_start(character: char) -> bool {
    character.is_ascii_alphabetic() || character == '_'
}

fn is_type_name_character(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '_' | '$')
}

fn is_type_argument_character(character: char) -> bool {
    is_type_name_character(character) || matches!(character, '+' | '-')
}

fn skip_space(text: &[char], index: usize) -> usize {
    index
        + text[index..]
            .iter()
            .take_while(|character| char::is_whitespace(**character))
            .count()
}

fn skip_argument(text: &[char], index: usize) -> Option<usize> {
    let length = text[index..]
        .iter()
        .take_while(|character| is_type_argument_character(**character))
        .count();
    (length > 0).then_some(index + length)
}

/// Python's `_UNQUOTED_MODEL_TYPE_PATTERN.fullmatch`: a name with optional `(arg, ...)`.
pub(crate) fn is_unquoted_type(value: &str) -> bool {
    let text: Vec<char> = value.chars().collect();
    if !text
        .first()
        .is_some_and(|character| is_type_name_start(*character))
    {
        return false;
    }
    let mut index = 1 + text[1..]
        .iter()
        .take_while(|character| is_type_name_character(**character))
        .count();
    if index == text.len() {
        return true;
    }
    index = skip_space(&text, index);
    if text.get(index) != Some(&'(') {
        return false;
    }
    index = skip_space(&text, index + 1);
    let Some(mut index) = skip_argument(&text, index) else {
        return false;
    };
    loop {
        let after_space = skip_space(&text, index);
        if text.get(after_space) != Some(&',') {
            index = after_space;
            break;
        }
        let Some(next) = skip_argument(&text, skip_space(&text, after_space + 1)) else {
            return false;
        };
        index = next;
    }
    text.get(index) == Some(&')') && index + 1 == text.len()
}

/// Python's `_render_model_type`: bare when unquoted-safe, else a double-quoted string.
pub(crate) fn render_model_type(value: &str) -> String {
    if is_unquoted_type(value) {
        return value.to_owned();
    }
    let escaped = value.replace('\\', "\\\\").replace('"', "\\\"");
    format!("\"{escaped}\"")
}

fn without_space(value: &str) -> String {
    value
        .chars()
        .filter(|character| !char::is_whitespace(*character))
        .collect()
}

/// Python's `_model_types_match`.
fn model_types_match(authored: &str, parsed: &str) -> bool {
    if str::to_lowercase(authored) == str::to_lowercase(parsed) {
        return true;
    }
    if !(is_unquoted_type(authored) && is_unquoted_type(parsed)) {
        return false;
    }
    str::to_lowercase(&without_space(authored)) == str::to_lowercase(&without_space(parsed))
}

fn is_header_word_character(character: char) -> bool {
    char::is_alphanumeric(character) || CONTRACT_HEADER_WORD_EXTRA.contains(&character)
}

/// The end of the header string at `start`, by the shared header string rules, or `end`.
fn quoted_value_end(text: &[char], start: usize, end: usize) -> usize {
    header_quoted_end(&text[..end], start).map_or(end, |value_end| value_end.min(end))
}

fn unquoted_type_value_end(text: &[char], start: usize, end: usize) -> usize {
    let mut index = start;
    let mut depth = 0_usize;
    let mut saw_open = false;
    while index < end {
        let character = text[index];
        if character == '(' {
            depth += 1;
            saw_open = true;
        } else if character == ')' {
            if depth == 0 {
                break;
            }
            depth -= 1;
        } else if depth == 0 && char::is_whitespace(character) {
            let next = index
                + text[index..end]
                    .iter()
                    .take_while(|character| char::is_whitespace(**character))
                    .count();
            if !saw_open && text.get(next) == Some(&'(') {
                index = next;
                continue;
            }
            break;
        } else if depth == 0 && character == ',' {
            break;
        }
        index += 1;
    }
    index
}

/// Python's `_declared_type_span`: the authored top-level `type` value matching `declared`.
pub(crate) fn declared_type_span(
    text: &[char],
    metadata: (usize, usize),
    declared: &str,
) -> Option<(usize, usize)> {
    let (metadata_start, metadata_end) = metadata;
    let key_length = CONTRACT_TYPE_KEY.chars().count();
    let mut index = metadata_start;
    let mut depth = 0_usize;
    while index < metadata_end {
        let character = text[index];
        if CONTRACT_QUOTES.contains(&character) {
            index = quoted_value_end(text, index, metadata_end);
            continue;
        }
        if CONTRACT_OPENERS.contains(&character) {
            depth += 1;
            index += 1;
            continue;
        }
        if CONTRACT_CLOSERS.contains(&character) {
            depth = depth.saturating_sub(1);
            index += 1;
            continue;
        }
        if depth > 0
            || str::to_lowercase(&slice(text, index, index + key_length)) != CONTRACT_TYPE_KEY
        {
            index += 1;
            continue;
        }
        let key_end = index + key_length;
        if (index > metadata_start && is_header_word_character(text[index - 1]))
            || (key_end < metadata_end && is_header_word_character(text[key_end]))
        {
            index = key_end;
            continue;
        }
        let mut value_start = key_end;
        while value_start < metadata_end && char::is_whitespace(text[value_start]) {
            value_start += 1;
        }
        let (value_end, authored) = match text.get(value_start) {
            Some(_) if opens_triple_quote(text, value_start) => {
                let value_end = quoted_value_end(text, value_start, metadata_end);
                let inner = slice(
                    text,
                    value_start + TRIPLE_QUOTE_LENGTH,
                    value_end.saturating_sub(TRIPLE_QUOTE_LENGTH),
                );
                (value_end, inner)
            }
            Some(quote) if CONTRACT_QUOTES.contains(quote) => {
                let value_end = quoted_value_end(text, value_start, metadata_end);
                let inner = slice(text, value_start + 1, value_end.saturating_sub(1));
                let authored = inner
                    .replace(&format!("\\{quote}"), &quote.to_string())
                    .replace("\\\\", "\\");
                (value_end, authored)
            }
            _ => {
                let value_end = unquoted_type_value_end(text, value_start, metadata_end);
                (value_end, slice(text, value_start, value_end))
            }
        };
        if model_types_match(&authored, declared) {
            return Some((value_start, value_end));
        }
        index = value_end;
    }
    None
}
