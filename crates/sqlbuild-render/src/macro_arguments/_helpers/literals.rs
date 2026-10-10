//! Python string and number literals: escapes, prefixes, underscores and radixes.

use crate::macro_arguments::_helpers::failures::{Failure, named_sequence, surrogate, syntax};
use crate::macro_arguments::_helpers::lexer::{NumberToken, StringPiece, is_name_start};
use crate::macro_arguments::constants::{BINARY_RADIX, DECIMAL_RADIX, HEX_RADIX, OCTAL_RADIX};
use crate::macro_arguments::types::ArgumentHost;

/// The string starting at the quote `start` under `prefix`, and the index after it.
pub(crate) fn string_body(
    host: &dyn ArgumentHost,
    text: &[char],
    start: usize,
    prefix: &str,
) -> Result<(StringPiece, usize), Failure> {
    let quote: char = text[start];
    let triple: bool = text.get(start + 1) == Some(&quote) && text.get(start + 2) == Some(&quote);
    let width: usize = if triple { 3 } else { 1 };
    let raw: bool = prefix.contains('r');
    let mut value: String = String::new();
    let mut index: usize = start + width;
    loop {
        let Some(&character) = text.get(index) else {
            return Err(syntax("a string is not closed", start));
        };
        if character == quote && (!triple || closes_triple(text, index, quote)) {
            index += width;
            break;
        }
        if !triple && matches!(character, '\n' | '\r') {
            return Err(syntax("a string is not closed before the line ends", start));
        }
        if character != '\\' {
            value.push(character);
            index += 1;
            continue;
        }
        let Some(&escaped) = text.get(index + 1) else {
            return Err(syntax("a string is not closed", start));
        };
        if raw {
            value.push('\\');
            value.push(escaped);
            index += 2;
            continue;
        }
        let (decoded, end) = escape(host, text, index)?;
        value.push_str(&decoded);
        index = end;
    }
    Ok((
        StringPiece {
            value,
            bytes: prefix.contains('b'),
            formatted: prefix.contains('f'),
        },
        index,
    ))
}

fn closes_triple(text: &[char], index: usize, quote: char) -> bool {
    text.get(index + 1) == Some(&quote) && text.get(index + 2) == Some(&quote)
}

/// The text the escape at the backslash `index` decodes to, and the index after it.
fn escape(
    host: &dyn ArgumentHost,
    text: &[char],
    index: usize,
) -> Result<(String, usize), Failure> {
    let escaped: char = text[index + 1];
    let simple: Option<char> = match escaped {
        '\\' => Some('\\'),
        '\'' => Some('\''),
        '"' => Some('"'),
        'a' => Some('\x07'),
        'b' => Some('\x08'),
        'f' => Some('\x0c'),
        'n' => Some('\n'),
        'r' => Some('\r'),
        't' => Some('\t'),
        'v' => Some('\x0b'),
        _ => None,
    };
    if let Some(character) = simple {
        return Ok((character.to_string(), index + 2));
    }
    let line_end: usize = if text.get(index + 2) == Some(&'\n') {
        index + 3
    } else {
        index + 2
    };
    match escaped {
        '\n' => Ok((String::new(), index + 2)),
        '\r' => Ok((String::new(), line_end)),
        '0'..='7' => {
            let digits: usize = text[index + 1..]
                .iter()
                .take(3)
                .take_while(|character| matches!(character, '0'..='7'))
                .count();
            let code: u32 = radix_value(&text[index + 1..index + 1 + digits], OCTAL_RADIX);
            Ok((
                char::from_u32(code).unwrap_or_default().to_string(),
                index + 1 + digits,
            ))
        }
        'x' => hex_escape(text, index, 2),
        'u' => hex_escape(text, index, 4),
        'U' => hex_escape(text, index, 8),
        'N' => named_escape(host, text, index),
        _ => Ok(("\\".to_owned(), index + 1)),
    }
}

fn hex_escape(text: &[char], index: usize, width: usize) -> Result<(String, usize), Failure> {
    let digits: &[char] = &text[index + 2..text.len().min(index + 2 + width)];
    if digits.len() < width || !digits.iter().all(char::is_ascii_hexdigit) {
        let escape: String = text[index..index + 2].iter().collect();
        return Err(syntax(
            &format!("a {escape} escape needs exactly {width} hex digits"),
            index,
        ));
    }
    let code: u32 = radix_value(digits, HEX_RADIX);
    let end: usize = index + 2 + width;
    if (0xD800..=0xDFFF).contains(&code) {
        let escape: String = text[index..end].iter().collect();
        return Err(surrogate(&escape, surrogate_pair(text, code, end), index));
    }
    let character: char = char::from_u32(code).ok_or_else(|| {
        let escape: String = text[index..end].iter().collect();
        syntax(&format!("{escape} is not a Unicode code point"), index)
    })?;
    Ok((character.to_string(), end))
}

fn named_escape(
    host: &dyn ArgumentHost,
    text: &[char],
    index: usize,
) -> Result<(String, usize), Failure> {
    let close: Option<usize> = (text.get(index + 2) == Some(&'{'))
        .then(|| {
            text[index + 3..]
                .iter()
                .position(|character| *character == '}')
        })
        .flatten();
    let Some(close) = close else {
        return Err(syntax("a \\N escape needs a {name}", index));
    };
    let name: String = text[index + 3..index + 3 + close].iter().collect();
    let named: String = host
        .character_named(&name)
        .ok_or_else(|| syntax(&format!("\\N{{{name}}} names no Unicode character"), index))?;
    let length: usize = named.chars().count();
    if length != 1 {
        return Err(named_sequence(&name, length, index));
    }
    Ok((named, index + 4 + close))
}

/// The code point a high surrogate `code` and a `\u` low surrogate escape at `next` spell.
fn surrogate_pair(text: &[char], code: u32, next: usize) -> Option<u32> {
    let high: bool = (0xD800..=0xDBFF).contains(&code);
    let digits: &[char] = text.get(next + 2..next + 6)?;
    let low: u32 = (high
        && text.get(next..next + 2) == Some(&['\\', 'u'][..])
        && digits.iter().all(char::is_ascii_hexdigit))
    .then(|| radix_value(digits, HEX_RADIX))?;
    (0xDC00..=0xDFFF)
        .contains(&low)
        .then(|| 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00))
}

fn radix_value(digits: &[char], radix: u32) -> u32 {
    digits.iter().fold(0, |total, digit| {
        total * radix + digit.to_digit(radix).unwrap_or_default()
    })
}

/// The number starting at `start` and the index after it.
pub(crate) fn number(text: &[char], start: usize) -> Result<(NumberToken, usize), Failure> {
    let prefixed: Option<u32> = (text[start] == '0')
        .then(|| match text.get(start + 1) {
            Some('x' | 'X') => Some(HEX_RADIX),
            Some('o' | 'O') => Some(OCTAL_RADIX),
            Some('b' | 'B') => Some(BINARY_RADIX),
            _ => None,
        })
        .flatten();
    if let Some(radix) = prefixed {
        let mut index: usize = start + 2;
        if text.get(index) == Some(&'_') {
            index += 1;
        }
        let (digits, end) = digit_part(text, index, radix, start)?;
        if digits.is_empty() {
            return Err(syntax(
                "a number has no digits after its base prefix",
                start,
            ));
        }
        let end: usize = reject_trailing_name(text, end, start)?;
        return Ok((NumberToken::Int { radix, digits }, end));
    }
    let (whole, mut index) = digit_part(text, start, DECIMAL_RADIX, start)?;
    let mut float: bool = false;
    let mut literal: String = whole.clone();
    if text.get(index) == Some(&'.') {
        float = true;
        literal.push('.');
        let (fraction, end) = digit_part(text, index + 1, DECIMAL_RADIX, start)?;
        literal.push_str(&fraction);
        index = end;
    }
    if matches!(text.get(index), Some('e' | 'E')) {
        let mut exponent_start: usize = index + 1;
        let mut exponent: String = String::from("e");
        if let Some(sign @ ('+' | '-')) = text.get(exponent_start) {
            exponent.push(*sign);
            exponent_start += 1;
        }
        let (digits, end) = digit_part(text, exponent_start, DECIMAL_RADIX, start)?;
        if digits.is_empty() {
            return Err(syntax("a number's exponent has no digits", start));
        }
        float = true;
        literal.push_str(&exponent);
        literal.push_str(&digits);
        index = end;
    }
    if matches!(text.get(index), Some('j' | 'J')) {
        let end: usize = reject_trailing_name(text, index + 1, start)?;
        return Ok((NumberToken::Complex, end));
    }
    let end: usize = reject_trailing_name(text, index, start)?;
    if float {
        return Ok((NumberToken::Float(literal), end));
    }
    if whole.len() > 1 && whole.starts_with('0') && whole.chars().any(|digit| digit != '0') {
        return Err(syntax(
            "leading zeros in a decimal integer are not allowed; use 0o for octal",
            start,
        ));
    }
    Ok((
        NumberToken::Int {
            radix: DECIMAL_RADIX,
            digits: whole,
        },
        end,
    ))
}

/// Digits in `radix` with single underscores between them, without the underscores.
fn digit_part(
    text: &[char],
    start: usize,
    radix: u32,
    number_start: usize,
) -> Result<(String, usize), Failure> {
    let mut digits: String = String::new();
    let mut index: usize = start;
    while let Some(&character) = text.get(index) {
        if character.is_digit(radix) {
            digits.push(character);
            index += 1;
        } else if character == '_'
            && !digits.is_empty()
            && text.get(index + 1).is_some_and(|next| next.is_digit(radix))
        {
            index += 1;
        } else if character == '_' || (character.is_ascii_digit() && radix < DECIMAL_RADIX) {
            return Err(syntax(
                "a number has a misplaced '_' or digit",
                number_start,
            ));
        } else {
            break;
        }
    }
    Ok((digits, index))
}

fn reject_trailing_name(text: &[char], end: usize, start: usize) -> Result<usize, Failure> {
    if text
        .get(end)
        .is_some_and(|next| is_name_start(*next) || next.is_ascii_digit())
    {
        return Err(syntax("a number runs into a name", start));
    }
    Ok(end)
}
