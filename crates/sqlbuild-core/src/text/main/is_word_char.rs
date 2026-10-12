//! A word character: a letter, a number or `_`.

/// Whether `character` is `_` or alphanumeric.
pub fn is_word_char(character: char) -> bool {
    character == '_' || char::is_alphanumeric(character)
}
