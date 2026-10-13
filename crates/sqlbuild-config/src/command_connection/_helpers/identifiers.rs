//! Snowflake warehouse identifier syntax.

use crate::command_connection::constants::MIN_QUOTED_IDENTIFIER_LENGTH;

/// Whether `text` fully matches `[A-Za-z_][A-Za-z0-9_$]*|"(?:[^"]|"")+"`.
pub(crate) fn is_warehouse_identifier(text: &str) -> bool {
    let mut characters = text.chars();
    let Some(first) = characters.next() else {
        return false;
    };
    if first.is_ascii_alphabetic() || first == '_' {
        return characters.all(|character| {
            character.is_ascii_alphanumeric() || character == '_' || character == '$'
        });
    }
    if first != '"' || text.len() < MIN_QUOTED_IDENTIFIER_LENGTH || !text.ends_with('"') {
        return false;
    }
    let interior: &str = &text[1..text.len() - 1];
    let mut quote_run: usize = 0;
    for character in interior.chars() {
        if character == '"' {
            quote_run += 1;
        } else if !quote_run.is_multiple_of(2) {
            return false;
        } else {
            quote_run = 0;
        }
    }
    quote_run.is_multiple_of(2)
}
