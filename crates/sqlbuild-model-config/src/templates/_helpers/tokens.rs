//! The Python template tokenizer, deferring wherever Python's `str.isspace` would decide.

use crate::templates::errors::TemplateError;
use crate::templates::models::TemplateFailure;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum TokenKind {
    Word(String),
    Text(String),
    Symbol(char),
    End,
}

/// One token and the character position it starts at; tokenized text is ASCII.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Token {
    pub(crate) kind: TokenKind,
    pub(crate) position: usize,
}

impl Token {
    /// Python's `token.value`: the word, the unquoted text, the symbol or nothing at the end.
    pub(crate) fn value(&self) -> String {
        match &self.kind {
            TokenKind::Word(text) | TokenKind::Text(text) => text.clone(),
            TokenKind::Symbol(symbol) => symbol.to_string(),
            TokenKind::End => String::new(),
        }
    }
}

const SYMBOLS: [char; 3] = ['(', ')', ','];
const ESCAPE: char = '\\';

/// Split one template expression into tokens; positions count characters, as Python's do.
pub(crate) fn tokenize(expression: &str) -> Result<Vec<Token>, TemplateFailure> {
    let characters: Vec<char> = expression.chars().collect();
    let mut tokens: Vec<Token> = Vec::new();
    let mut index: usize = 0;
    while let Some(&character) = characters.get(index) {
        if !character.is_ascii() {
            return Err(TemplateFailure::Unsupported);
        }
        let position: usize = index;
        if is_python_space(character) {
            index += 1;
        } else if SYMBOLS.contains(&character) {
            tokens.push(Token {
                kind: TokenKind::Symbol(character),
                position,
            });
            index += 1;
        } else if let Some(quote_name) = quote_name(character) {
            let (text, end) = quoted_text(&characters, index, quote_name)?;
            tokens.push(Token {
                kind: TokenKind::Text(text),
                position,
            });
            index = end;
        } else {
            let mut word = String::new();
            while let Some(&next) = characters.get(index) {
                if !next.is_ascii() {
                    return Err(TemplateFailure::Unsupported);
                }
                if is_python_space(next) || SYMBOLS.contains(&next) || quote_name(next).is_some() {
                    break;
                }
                word.push(next);
                index += 1;
            }
            tokens.push(Token {
                kind: TokenKind::Word(word),
                position,
            });
        }
    }
    tokens.push(Token {
        kind: TokenKind::End,
        position: characters.len(),
    });
    Ok(tokens)
}

/// The text quoted at `start` and the index after its closing quote.
fn quoted_text(
    characters: &[char],
    start: usize,
    quote_name: &'static str,
) -> Result<(String, usize), TemplateFailure> {
    let quote: char = characters[start];
    let mut text = String::new();
    let mut index: usize = start + 1;
    while let Some(&character) = characters.get(index) {
        if character == ESCAPE {
            let escaped: char = *characters.get(index + 1).ok_or(TemplateFailure::Invalid(
                TemplateError::UnterminatedEscape(index),
            ))?;
            text.push(escaped);
            index += 2;
        } else if character == quote {
            return Ok((text, index + 1));
        } else {
            text.push(character);
            index += 1;
        }
    }
    Err(TemplateFailure::Invalid(TemplateError::UnterminatedString(
        quote_name, start,
    )))
}

fn quote_name(character: char) -> Option<&'static str> {
    match character {
        '\'' => Some("single"),
        '"' => Some("double"),
        _ => None,
    }
}

/// ASCII characters Python's `str.isspace` accepts, including the information separators.
fn is_python_space(character: char) -> bool {
    matches!(character, '\t'..='\r' | '\u{1c}'..='\u{1f}' | ' ')
}
