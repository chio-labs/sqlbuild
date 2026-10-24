//! Quoted header values: their extent, escapes, and lines split outside them.

use sqlbuild_core::text::main::python_isalnum::python_isalnum;
use sqlbuild_core::text::main::python_isspace::python_isspace;

use sqlbuild_sqltext::header_strings::main::header_quoted_end::header_quoted_end;

use crate::dsl_headers::_helpers::text::{is_alpha, string};
use crate::dsl_headers::constants::{DESCRIPTION_KEY, QUOTES};

/// The offset just past the quoted value that opens at `start`, or the end when it never closes.
pub(crate) fn quoted_value_end(text: &[char], start: usize) -> usize {
    header_quoted_end(text, start).map_or(text.len(), |end| end.min(text.len()))
}

/// The span of the top-level `description` string value inside the header parentheses.
pub(crate) fn description_value_span(text: &[char]) -> Option<(usize, usize)> {
    let mut delimiters: Vec<char> = Vec::new();
    let mut index: usize = 0;
    while index < text.len() {
        let character: char = text[index];
        if QUOTES.contains(&character) {
            index = quoted_value_end(text, index);
            continue;
        }
        let closing: Option<char> = match character {
            '(' => Some(')'),
            '[' => Some(']'),
            '{' => Some('}'),
            _ => None,
        };
        if let Some(closing) = closing {
            delimiters.push(closing);
            index += 1;
            continue;
        }
        if delimiters.last() == Some(&character) {
            delimiters.pop();
            index += 1;
            continue;
        }
        if delimiters == [')'] && (is_alpha(character) || character == '_') {
            let mut word_end: usize = index + 1;
            while word_end < text.len() && (python_isalnum(text[word_end]) || text[word_end] == '_')
            {
                word_end += 1;
            }
            if string(&text[index..word_end]).to_lowercase() == DESCRIPTION_KEY {
                let mut quote_start: usize = word_end;
                while quote_start < text.len() && python_isspace(text[quote_start]) {
                    quote_start += 1;
                }
                if quote_start < text.len() && QUOTES.contains(&text[quote_start]) {
                    let quote_end: usize = quoted_value_end(text, quote_start);
                    return Some((quote_start + 1, quote_end - 1));
                }
            }
            index = word_end;
            continue;
        }
        index += 1;
    }
    None
}

/// `text` split on newlines that are outside quoted values.
pub(crate) fn split_outside_quotes(text: &[char]) -> Vec<&[char]> {
    let mut lines: Vec<&[char]> = Vec::new();
    let mut line_start: usize = 0;
    let mut index: usize = 0;
    while index < text.len() {
        let character: char = text[index];
        if QUOTES.contains(&character) {
            index = quoted_value_end(text, index);
            continue;
        }
        if character == '\n' {
            lines.push(&text[line_start..index]);
            line_start = index + 1;
        }
        index += 1;
    }
    lines.push(&text[line_start..]);
    lines
}
