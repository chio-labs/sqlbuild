//! Python's `str.isalnum` for one character.

use crate::text::_helpers::python_tables::{NOT_PYTHON_ALNUM, in_ranges};

/// Whether Python's `str.isalnum` accepts `character`.
#[must_use]
pub fn python_isalnum(character: char) -> bool {
    character.is_alphanumeric() && !in_ranges(&NOT_PYTHON_ALNUM, character)
}
