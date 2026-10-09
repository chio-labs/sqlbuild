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
        if let Some(call) = nested.iter().position(|(start, _)| *start == index) {
            tokens.push(Token {
                kind: TokenKind::Nested(call),
                position: index,
            });
            index = nested[call].1;
            continue;
        }
        let character: char = text[index];
        match character {
            ' ' | '\t' | '\x0c' | '\n' | '\r' => index += 1,
            '#' => {
                while index < text.len() && !matches!(text[index], '\n' | '\r') {
                    index += 1;
                }
            }
            '\\' => index = line_continuation(text, index)?,
            '\'' | '"' => {
                let (piece, end) = string_body(host, text, index, "")?;
                tokens.push(Token {
                    kind: TokenKind::Str(piece),
                    position: index,
                });
                index = end;
            }
            '0'..='9' => index = push_number(text, index, &mut tokens)?,
            '.' if text.get(index + 1).is_some_and(char::is_ascii_digit) => {
                index = push_number(text, index, &mut tokens)?;
            }
            _ if is_name_start(character) => index = push_name(host, text, index, &mut tokens)?,
            _ => index = push_operator(text, index, &mut tokens)?,
        }
    }
    tokens.push(Token {
        kind: TokenKind::End,
        position: text.len(),
    });
    Ok(tokens)
}

fn line_continuation(text: &[char], index: usize) -> Result<usize, Failure> {
    match (text.get(index + 1), text.get(index + 2)) {
        (Some('\n'), _) => Ok(index + 2),
        (Some('\r'), Some('\n')) => Ok(index + 3),
        (Some('\r'), _) => Ok(index + 2),
        _ => Err(syntax("a '\\' outside a string must end the line", index)),
    }
}

fn push_number(text: &[char], index: usize, tokens: &mut Vec<Token>) -> Result<usize, Failure> {
    let (token, end) = number(text, index)?;
    tokens.push(Token {
        kind: TokenKind::Number(token),
        position: index,
    });
    Ok(end)
}

fn push_name(
    host: &dyn ArgumentHost,
    text: &[char],
    index: usize,
    tokens: &mut Vec<Token>,
) -> Result<usize, Failure> {
    let mut end: usize = index;
    while end < text.len() && is_name_continue(text[end]) {
        end += 1;
    }
    let word: String = text[index..end].iter().collect();
    let lowered: String = word.to_ascii_lowercase();
    if matches!(text.get(end), Some('\'' | '"')) && STRING_PREFIXES.contains(&lowered.as_str()) {
        let (piece, string_end) = string_body(host, text, end, &lowered)?;
        tokens.push(Token {
            kind: TokenKind::Str(piece),
            position: index,
        });
        return Ok(string_end);
    }
    let name: String = if word.is_ascii() {
        word
    } else {
        host.identifier(&word).ok_or_else(|| {
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
        })?
    };
    tokens.push(Token {
        kind: TokenKind::Name(name),
        position: index,
    });
    Ok(end)
}

fn push_operator(text: &[char], index: usize, tokens: &mut Vec<Token>) -> Result<usize, Failure> {
    if text[index] == '\0' {
        return Err(syntax("a NUL character is not allowed", index));
    }
    let rest: String = text[index..text.len().min(index + 3)].iter().collect();
    let kind: TokenKind = OPERATORS
        .iter()
        .find(|operator| rest.starts_with(**operator))
        .map_or_else(
            || TokenKind::Other,
            |operator| TokenKind::Operator(operator),
        );
    let width: usize = match &kind {
        TokenKind::Operator(operator) => operator.len(),
        _ => 1,
    };
    tokens.push(Token {
        kind,
        position: index,
    });
    Ok(index + width)
}

/// Python's tokenizer reads ASCII letters, `_` and any non-ASCII character into a name.
pub(crate) fn is_name_start(character: char) -> bool {
    character.is_ascii_alphabetic() || character == '_' || !character.is_ascii()
}

fn is_name_continue(character: char) -> bool {
    is_name_start(character) || character.is_ascii_digit()
}
