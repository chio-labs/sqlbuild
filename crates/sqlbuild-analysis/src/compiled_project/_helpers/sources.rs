//! Where a model's authored settings live: opt-out keys and legacy schema declarations.

use sqlbuild_core::text::main::is_word_char::is_word_char;

use crate::compiled_project::constants::{NEWLINE, OPT_OUT_KEYS};
use crate::compiled_project::models::TextPosition;

/// `_text_location`: the first whole-word opt-out key at or after character `start`.
pub(crate) fn opt_out_position(text: &str, start: usize) -> TextPosition {
    let characters: Vec<char> = text.chars().collect();
    let mut offset: usize = 0;
    for index in start..characters.len() {
        if starts_key(&characters, index) {
            offset = index;
            break;
        }
    }
    char_position(&characters, offset)
}

/// The one-based line and column of character `offset`.
pub(crate) fn char_position(characters: &[char], offset: usize) -> TextPosition {
    let offset: usize = offset.min(characters.len());
    let mut line: usize = 1;
    let mut line_start: usize = 0;
    for (index, character) in characters[..offset].iter().enumerate() {
        if *character == NEWLINE {
            line += 1;
            line_start = index + 1;
        }
    }
    TextPosition {
        line,
        column: offset - line_start + 1,
    }
}

/// Whether an opt-out key starts at `index` with a word boundary on both sides.
fn starts_key(characters: &[char], index: usize) -> bool {
    if index > 0 && is_word_char(characters[index - 1]) {
        return false;
    }
    for key in OPT_OUT_KEYS {
        let end: usize = index + key.chars().count();
        if end > characters.len() || !characters[index..end].iter().copied().eq(key.chars()) {
            continue;
        }
        if characters.get(end).is_none_or(|&next| !is_word_char(next)) {
            return true;
        }
    }
    false
}
