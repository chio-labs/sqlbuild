//! Read a bare MODEL header word as `true`, `false`, `null`, a number or text.

use crate::compiler::_helpers::model_headers::words::{
    FALSE_WORD, NULL_WORD, TRUE_WORD, float, integer, signed,
};
use crate::compiler::models::HeaderWord;

/// Python's `_parse_word_value`: booleans, null, `^[+-]?\d+$` integers, decimal floats, or text.
pub fn header_word_value(word: &str) -> HeaderWord {
    match word {
        TRUE_WORD => return HeaderWord::Bool(true),
        FALSE_WORD => return HeaderWord::Bool(false),
        NULL_WORD => return HeaderWord::Null,
        _ => {}
    }
    let (sign, body) = signed(word.strip_suffix('\n').unwrap_or(word));
    integer(sign, body)
        .or_else(|| float(sign, body))
        .unwrap_or(HeaderWord::Text)
}
