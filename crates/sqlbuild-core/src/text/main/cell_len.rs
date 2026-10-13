//! The terminal cells a string occupies.

use crate::text::main::char_cells::char_cells;

/// The terminal cells `text` occupies.
#[must_use]
pub fn cell_len(text: &str) -> usize {
    text.chars().map(char_cells).sum()
}
