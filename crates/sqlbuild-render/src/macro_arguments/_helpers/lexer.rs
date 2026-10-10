//! Python's tokenizer for the literal subset macro arguments use, over code points.

use crate::macro_arguments::_helpers::failures::{Failure, syntax};
use crate::macro_arguments::_helpers::literals::{number, string_body};
use crate::macro_arguments::types::ArgumentHost;

const STRING_PREFIXES: [&str; 8] = ["r", "u", "b", "f", "br", "rb", "fr", "rf"];
const OPERATORS: [&str; 15] = [
    "**", "...", "(", ")", "[", "]", "{", "}", ",", ":", "=", "*", "-", "+", ".",
];

/// One literal string piece; adjacent pieces concatenate.
#[derive(Clone, Debug)]
pub(crate) struct StringPiece {
    pub(crate) value: String,
    pub(crate) bytes: bool,
    pub(crate) formatted: bool,
}

/// A number token as Python reads it.
#[derive(Clone, Debug)]
pub(crate) enum NumberToken {
    Int { radix: u32, digits: String },
    Float(String),
    Complex,
}

#[derive(Clone, Debug)]
pub(crate) enum TokenKind {
    Str(StringPiece),
    Number(NumberToken),
    Name(String),
    Nested(usize),
    Operator(&'static str),
    /// Any other operator, which no supported argument uses.
    Other,
    End,
}

#[derive(Clone, Debug)]
pub(crate) struct Token {
    pub(crate) kind: TokenKind,
    pub(crate) position: usize,
}

/// Tokenize `text`; `nested` are the `[start, end)` code point spans of nested macro calls.
pub(crate) fn tokenize(
    host: &dyn ArgumentHost,
    text: &[char],
    nested: &[(usize, usize)],
) -> Result<Vec<Token>, Failure> {
    let mut tokens: Vec<Token> = Vec::new();
    let mut index: usize = 0;
    while index < text.len() {
        let (kind, end): (Option<TokenKind>, usize) = next_token(host, text, nested, index)?;
        if let Some(kind) = kind {
            tokens.push(Token {
                kind,
                position: index,
            });
        }
        index = end;
    }
    tokens.push(Token {
        kind: TokenKind::End,
        position: text.len(),
    });
    Ok(tokens)
}

/// The token starting at `index`, or `None` for whitespace and comments, and where it ends.
fn next_token(
    host: &dyn ArgumentHost,
    text: &[char],
    nested: &[(usize, usize)],
    index: usize,
) -> Result<(Option<TokenKind>, usize), Failure> {
    if let Some(call) = nested.iter().position(|(start, _)| *start == index) {
        return Ok((Some(TokenKind::Nested(call)), nested[call].1));
    }
    let character: char = text[index];
    let (kind, end): (TokenKind, usize) = match character {
        ' ' | '\t' | '\x0c' | '\n' | '\r' => return Ok((None, index + 1)),
        '#' => {
            let end: usize = text[index..]
                .iter()
                .position(|character| matches!(character, '\n' | '\r'))
                .map_or(text.len(), |offset| index + offset);
            return Ok((None, end));
        }
        '\\' => return Ok((None, line_continuation(text, index)?)),
        '\'' | '"' => {
            let (piece, end) = string_body(host, text, index, "")?;
            (TokenKind::Str(piece), end)
        }
        '0'..='9' => number_token(text, index)?,
        '.' if text.get(index + 1).is_some_and(char::is_ascii_digit) => number_token(text, index)?,
        _ if is_name_start(character) => name_token(host, text, index)?,
        _ => operator_token(text, index)?,
    };
    Ok((Some(kind), end))
}

fn line_continuation(text: &[char], index: usize) -> Result<usize, Failure> {
    match (text.get(index + 1), text.get(index + 2)) {
        (Some('\n'), _) => Ok(index + 2),
        (Some('\r'), Some('\n')) => Ok(index + 3),
        (Some('\r'), _) => Ok(index + 2),
        _ => Err(syntax("a '\\' outside a string must end the line", index)),
    }
}

fn number_token(text: &[char], index: usize) -> Result<(TokenKind, usize), Failure> {
    let (token, end) = number(text, index)?;
    Ok((TokenKind::Number(token), end))
}

fn name_token(
    host: &dyn ArgumentHost,
    text: &[char],
    index: usize,
) -> Result<(TokenKind, usize), Failure> {
    let end: usize = text[index..]
        .iter()
        .position(|character| !is_name_continue(*character))
        .map_or(text.len(), |offset| index + offset);
    let word: String = text[index..end].iter().collect();
    let lowered: String = word.to_ascii_lowercase();
    if matches!(text.get(end), Some('\'' | '"')) && STRING_PREFIXES.contains(&lowered.as_str()) {
        let (piece, string_end) = string_body(host, text, end, &lowered)?;
        return Ok((TokenKind::Str(piece), string_end));
    }
    if word.is_ascii() {
        return Ok((TokenKind::Name(word), end));
    }
    let name: String = host.identifier(&word).ok_or_else(|| {
        let invalid: char = text[index..end]
            .iter()
            .copied()
            .find(|character| {
                !character.is_ascii() && host.identifier(&format!("a{character}")).is_none()
            })
            .unwrap_or(text[index]);
        syntax(
            &format!(
                "the character '{invalid}' (U+{:04X}) is not valid in a name",
                u32::from(invalid)
            ),
            index,
        )
    })?;
    Ok((TokenKind::Name(name), end))
}

fn operator_token(text: &[char], index: usize) -> Result<(TokenKind, usize), Failure> {
    if text[index] == '\0' {
        return Err(syntax("a NUL character is not allowed", index));
    }
    let rest: String = text[index..text.len().min(index + 3)].iter().collect();
    Ok(OPERATORS
        .iter()
        .find(|operator| rest.starts_with(**operator))
        .map_or((TokenKind::Other, index + 1), |operator| {
            (TokenKind::Operator(operator), index + operator.len())
        }))
}

/// Python's tokenizer reads ASCII letters, `_` and any non-ASCII character into a name.
pub(crate) fn is_name_start(character: char) -> bool {
    character.is_ascii_alphabetic() || character == '_' || !character.is_ascii()
}

fn is_name_continue(character: char) -> bool {
    is_name_start(character) || character.is_ascii_digit()
}
