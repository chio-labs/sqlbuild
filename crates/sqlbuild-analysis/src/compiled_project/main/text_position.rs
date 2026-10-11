use crate::compiled_project::_helpers::sources::char_position;
use crate::compiled_project::models::TextPosition;

/// The one-based line and column of character `offset` in `text`.
pub fn text_position(text: &str, offset: usize) -> TextPosition {
    let characters: Vec<char> = text.chars().collect();
    char_position(&characters, offset)
}
