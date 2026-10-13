//! Quoted header values: their extent, escapes, and lines split outside them.

use sqlbuild_core::text::main::python_isalnum::python_isalnum;
use sqlbuild_core::text::main::python_isspace::python_isspace;

use crate::dsl_headers::_helpers::text::{is_alpha, string};
use crate::dsl_headers::constants::{DESCRIPTION_KEY, ESCAPE, QUOTES};

const MAX_CODEPOINT: u32 = 0x0010_FFFF;
const SURROGATES: std::ops::RangeInclusive<u32> = 0xD800..=0xDFFF;

/// The offset just past the quoted value that opens at `start`.
pub(crate) fn quoted_value_end(text: &[char], start: usize) -> usize {
    let quote: char = text[start];
    let mut index: usize = start + 1;
    while index < text.len() {
        if text[index] == ESCAPE && index + 1 < text.len() {
            index += 2;
            continue;
        }
        if text[index] == quote {
            return index + 1;
        }
        index += 1;
    }
    text.len()
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

/// The text of a quoted description value with its escapes decoded.
pub(crate) fn decode_description(value: &[char], quote: char) -> Vec<char> {
    let mut decoded: Vec<char> = Vec::with_capacity(value.len());
    let mut index: usize = 0;
    while index < value.len() {
        let character: char = value[index];
        if character != ESCAPE || index + 1 >= value.len() {
            decoded.push(character);
            index += 1;
            continue;
        }
        let escaped: char = value[index + 1];
        if escaped == ESCAPE || escaped == quote {
            decoded.push(escaped);
            index += 2;
            continue;
        }
        let simple: Option<char> = match escaped {
            'b' => Some('\u{8}'),
            'f' => Some('\u{c}'),
            'n' => Some('\n'),
            'r' => Some('\r'),
            't' => Some('\t'),
            _ => None,
        };
        if let Some(simple) = simple {
            decoded.push(simple);
            index += 2;
            continue;
        }
        let width: usize = match escaped {
            'u' => 4,
            'U' => 8,
            _ => 0,
        };
        let digits: &[char] = super::text::slice(value, index + 2, index + 2 + width);
        if width > 0 && digits.len() == width && digits.iter().all(char::is_ascii_hexdigit) {
            let codepoint: Option<char> = match u32::from_str_radix(&string(digits), 16) {
                Ok(codepoint) if codepoint <= MAX_CODEPOINT && !SURROGATES.contains(&codepoint) => {
                    char::from_u32(codepoint)
                }
                Ok(_) | Err(_) => None,
            };
            if let Some(decoded_character) = codepoint {
                decoded.push(decoded_character);
                index += width + 2;
                continue;
            }
        }
        decoded.extend([ESCAPE, escaped]);
        index += 2;
    }
    decoded
}

/// `value` with backslashes and `quote` escaped for a quoted header value.
pub(crate) fn escape_quoted(value: &[char], quote: char) -> Vec<char> {
    let mut escaped: Vec<char> = Vec::with_capacity(value.len());
    for character in value {
        if *character == ESCAPE || *character == quote {
            escaped.push(ESCAPE);
        }
        escaped.push(*character);
    }
    escaped
}

/// `text` split on newlines that are outside quoted values.
pub(crate) fn split_outside_quotes(text: &[char]) -> Vec<&[char]> {
    let mut lines: Vec<&[char]> = Vec::new();
    let mut line_start: usize = 0;
    let mut in_quote: Option<char> = None;
    let mut index: usize = 0;
    while index < text.len() {
        let character: char = text[index];
        if let Some(quote) = in_quote {
            if character == ESCAPE && index + 1 < text.len() {
                index += 2;
                continue;
            }
            if character == quote {
                in_quote = None;
            }
            index += 1;
            continue;
        }
        if QUOTES.contains(&character) {
            in_quote = Some(character);
        } else if character == '\n' {
            lines.push(&text[line_start..index]);
            line_start = index + 1;
        }
        index += 1;
    }
    lines.push(&text[line_start..]);
    lines
}
