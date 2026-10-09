//! The Python template tokenizer.

use crate::templates::errors::TemplateError;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use crate::templates::models::TemplateFailure;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum TokenKind {
    Word(String),
    Text(String),
    Symbol(char),
    End,
}

/// One token and its character position in the expression.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Token {
    pub(crate) kind: TokenKind,
    pub(crate) position: usize,
}

impl Token {
    /// Return the token's value as Python's error messages show it.
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

/// Split one template expression into tokens.
pub(crate) fn tokenize(expression: &str) -> Result<Vec<Token>, TemplateFailure> {
    let characters: Vec<char> = expression.chars().collect();
    let mut tokens: Vec<Token> = Vec::new();
    let mut index = 0;
    while let Some(&character) = characters.get(index) {
        if is_python_space(character) {
            index += 1;
        } else if SYMBOLS.contains(&character) {
            tokens.push(Token {
                kind: TokenKind::Symbol(character),
                position: index,
            });
            index += 1;
        } else if is_quote(character) {
            let (text, next) = quoted_text(&characters, index)?;
            tokens.push(Token {
                kind: TokenKind::Text(text),
                position: index,
            });
            index = next;
        } else {
            let start = index;
            while let Some(&next) = characters.get(index) {
                if is_python_space(next) || SYMBOLS.contains(&next) || is_quote(next) {
                    break;
                }
                index += 1;
            }
            tokens.push(Token {
                kind: TokenKind::Word(characters[start..index].iter().collect()),
                position: start,
            });
        }
    }
    tokens.push(Token {
        kind: TokenKind::End,
        position: characters.len(),
    });
    Ok(tokens)
}

fn quoted_text(characters: &[char], start: usize) -> Result<(String, usize), TemplateFailure> {
    let quote = characters[start];
    let mut text = String::new();
    let mut index = start + 1;
    while let Some(&character) = characters.get(index) {
        if character == ESCAPE {
            let Some(&escaped) = characters.get(index + 1) else {
                return Err(TemplateFailure::Invalid(
                    TemplateError::UnterminatedEscape { position: index },
                ));
            };
            text.push(escaped);
            index += 2;
        } else if character == quote {
            return Ok((text, index + 1));
        } else {
            text.push(character);
            index += 1;
        }
    }
    let quote = if quote == '\'' { "single" } else { "double" };
    Err(TemplateFailure::Invalid(
        TemplateError::UnterminatedString {
            quote,
            position: start,
        },
    ))
}

fn is_quote(character: char) -> bool {
    matches!(character, '\'' | '"')
}
