//! Character checks applied before parsing.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::{ConfigError, ConfigErrorKind};

/// Whether YAML 1.2 allows `character` in a stream (`c-printable`).
fn is_printable(character: char) -> bool {
    matches!(
        character,
        '\t' | '\n' | '\r' | ' '..='~' | '\u{85}' | '\u{a0}'..='\u{d7ff}' | '\u{e000}'..='\u{fffd}'
    ) || character >= '\u{10000}'
}

/// The text without one byte order mark at the very start.
pub(crate) fn without_byte_order_mark(text: &str) -> &str {
    text.strip_prefix(BYTE_ORDER_MARK).unwrap_or(text)
}

/// Reject characters YAML does not allow, at their one-based line and column.
pub(crate) fn check_characters(text: &str) -> Result<(), ConfigError> {
    let Some((index, character)) = text
        .char_indices()
        .find(|(_, character)| !is_printable(*character))
    else {
        return Ok(());
    };
    let before = &text[..index];
    let line_start = before.rfind('\n').map_or(0, |newline| newline + 1);
    Err(ConfigError::new(
        ConfigErrorKind::Syntax,
        format!("unacceptable character {:#x}", u32::from(character)),
    )
    .at(
        before.matches('\n').count() + 1,
        before[line_start..].chars().count() + 1,
    ))
}
