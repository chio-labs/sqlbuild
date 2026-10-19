//! `ansi_free_text`: output bytes as the text a command-output record's `message` holds.

use crate::command_output::_helpers::text::strip_ansi;

/// `data` without terminal control sequences, decoded as UTF-8 with invalid bytes replaced.
#[must_use]
pub fn ansi_free_text(data: &[u8]) -> String {
    String::from_utf8_lossy(&strip_ansi(data)).into_owned()
}
