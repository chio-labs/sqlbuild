//! Python's `str.isspace` for one character.

use crate::text::constants::PYTHON_SEPARATOR_CONTROLS;

/// Whether Python's `str.isspace` accepts `character`.
#[must_use]
pub fn python_isspace(character: char) -> bool {
    character.is_whitespace() || PYTHON_SEPARATOR_CONTROLS.contains(&character)
}
