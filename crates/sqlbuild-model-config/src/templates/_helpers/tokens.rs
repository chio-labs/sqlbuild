//! The Python template tokenizer, deferring wherever Python's `str.isspace` would decide.

use crate::templates::models::TemplateFailure;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Token {
    Word(String),
    Text(String),
    Symbol(char),
    End,
}

const SYMBOLS: [char; 3] = ['(', ')', ','];
const ESCAPE: char = '\\';

/// Split one template expression into tokens.
pub(crate) fn tokenize(expression: &str) -> Result<Vec<Token>, TemplateFailure> {
    let mut tokens: Vec<Token> = Vec::new();
    let mut characters = expression.chars().peekable();
    while let Some(&character) = characters.peek() {
        if !character.is_ascii() {
            return Err(TemplateFailure::Unsupported);
        }
        if is_python_space(character) {
            characters.next();
        } else if SYMBOLS.contains(&character) {
            tokens.push(Token::Symbol(character));
            characters.next();
        } else if is_quote(character) {
            characters.next();
            tokens.push(Token::Text(quoted_text(&mut characters, character)?));
        } else {
            let mut word = String::new();
            while let Some(&next) = characters.peek() {
                if !next.is_ascii() {
                    return Err(TemplateFailure::Unsupported);
                }
                if is_python_space(next) || SYMBOLS.contains(&next) || is_quote(next) {
                    break;
                }
                word.push(next);
                characters.next();
            }
            tokens.push(Token::Word(word));
        }
    }
    tokens.push(Token::End);
    Ok(tokens)
}

fn quoted_text(
    characters: &mut impl Iterator<Item = char>,
    quote: char,
) -> Result<String, TemplateFailure> {
    let mut text = String::new();
    while let Some(character) = characters.next() {
        if character == ESCAPE {
            text.push(characters.next().ok_or(TemplateFailure::Invalid)?);
        } else if character == quote {
            return Ok(text);
        } else {
            text.push(character);
        }
    }
    Err(TemplateFailure::Invalid)
}

fn is_quote(character: char) -> bool {
    matches!(character, '\'' | '"')
}

/// ASCII characters Python's `str.isspace` accepts, including the information separators.
fn is_python_space(character: char) -> bool {
    matches!(character, '\t'..='\r' | '\u{1c}'..='\u{1f}' | ' ')
}
