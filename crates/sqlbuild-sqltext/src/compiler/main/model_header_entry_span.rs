//! Where one top-level `key value` entry of a MODEL header is authored.

use crate::compiler::_helpers::model_headers::matching::match_one;
use crate::compiler::_helpers::model_headers::tokenization::{
    HeaderToken, SYMBOL_TOKEN, WORD_TOKEN, tokenize_one,
};
use sqlbuild_core::constants::{CLOSE_PAREN, OPEN_PAREN};
use sqlbuild_core::text::main::is_python_space::is_python_space;

/// Code-point offsets of the entry from its key to its value's end, or the tokenizer's error.
pub fn model_header_entry_span(
    contents: &str,
    key: &str,
) -> Result<Option<(usize, usize)>, String> {
    let Some((header_start, header_end, _)) = match_one(contents) else {
        return Ok(None);
    };
    let characters: Vec<char> = contents.chars().collect();
    let header: String = characters[header_start..header_end].iter().collect();
    let tokens: Vec<HeaderToken> = tokenize_one(&header)?;
    let mut depth: i64 = 0;
    for (index, (kind, value, position)) in tokens.iter().enumerate() {
        let symbol: bool = *kind == SYMBOL_TOKEN;
        if symbol && value == OPEN_PAREN {
            depth += 1;
        } else if symbol && value == CLOSE_PAREN {
            depth -= 1;
        } else if depth == 0 && *kind == WORD_TOKEN && value == key && index + 2 < tokens.len() {
            let start: usize = header_start + position;
            let mut end: usize = header_start + tokens[index + 2].2;
            while end > start && is_python_space(characters[end - 1]) {
                end -= 1;
            }
            return Ok(Some((start, end)));
        }
    }
    Ok(None)
}
