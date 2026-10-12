//! Whether one character is a letter.

/// Whether `character` is alphabetic and not a number, so letter-like numerals such as `Ⅻ` are not.
pub fn is_python_alpha(character: char) -> bool {
    character.is_alphabetic() && !character.is_numeric()
}
