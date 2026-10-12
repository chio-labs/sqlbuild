//! Whether one character is a letter or a number.

/// Whether `character` is alphanumeric under Unicode.
pub fn is_python_alnum(character: char) -> bool {
    character.is_alphanumeric()
}
