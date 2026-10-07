//! PyYAML's reader checks, applied before parsing.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::{ConfigError, ConfigErrorKind};
use crate::yaml::constants::{
    DIRECTIVE_INDICATOR, DOCUMENT_END_MARKER, LOADER_DEPENDENT_CHARACTERS, PYTHON_ONLY_LINE_BREAKS,
};

/// Whether PyYAML's reader accepts `character` (`Reader.NON_PRINTABLE` does not match it).
fn is_printable(character: char) -> bool {
    matches!(
        character,
        '\t' | '\n' | '\r' | ' '..='~' | '\u{85}' | '\u{a0}'..='\u{d7ff}' | '\u{e000}'..='\u{fffd}'
    ) || character >= '\u{10000}'
}

/// Whether a line holds only whitespace or a comment.
fn is_blank_or_comment(line: &str) -> bool {
    let content = line.trim_start_matches([' ', '\r']);
    content.is_empty() || content.starts_with('#')
}

/// Whether the first token of the stream is a `...` document end marker, which PyYAML rejects.
fn starts_with_document_end(text: &str) -> bool {
    text.split('\n')
        .find(|line| !is_blank_or_comment(line))
        .and_then(|line| line.strip_prefix(DOCUMENT_END_MARKER))
        .is_some_and(|rest| rest.is_empty() || rest.starts_with([' ', '\r']))
}

/// The text PyYAML's scanner reads: it skips one byte order mark at the very start.
pub(crate) fn without_byte_order_mark(text: &str) -> &str {
    text.strip_prefix(BYTE_ORDER_MARK).unwrap_or(text)
}

/// The one-based line and column of the character at byte `index`.
fn position_of(text: &str, index: usize) -> (usize, usize) {
    let before = &text[..index];
    let line_start = before.rfind('\n').map_or(0, |newline| newline + 1);
    (
        before.matches('\n').count() + 1,
        before[line_start..].chars().count() + 1,
    )
}

fn error_at(text: &str, index: usize, kind: ConfigErrorKind, message: String) -> ConfigError {
    let (line, column) = position_of(text, index);
    ConfigError::new(kind, message).at(line, column)
}

/// The byte index where the first line of `text` that `matches` starts.
fn line_index(text: &str, matches: impl Fn(&str) -> bool) -> Option<usize> {
    let mut index = 0;
    for line in text.split('\n') {
        if matches(line) {
            return Some(index);
        }
        index += line.len() + 1;
    }
    None
}

/// Reject what PyYAML's reader rejects, and the characters PyYAML and LibYAML read differently.
pub(crate) fn check_characters(text: &str) -> Result<(), ConfigError> {
    if let Some((index, character)) = text
        .char_indices()
        .find(|(_, character)| !is_printable(*character))
    {
        return Err(error_at(
            text,
            index,
            ConfigErrorKind::Syntax,
            format!("unacceptable character {:#x}", u32::from(character)),
        ));
    }
    if let Some(index) = text.find(PYTHON_ONLY_LINE_BREAKS) {
        return Err(error_at(
            text,
            index,
            ConfigErrorKind::Unsupported,
            "NEL, LINE SEPARATOR and PARAGRAPH SEPARATOR line breaks".to_owned(),
        ));
    }
    if let Some(index) = text.find(LOADER_DEPENDENT_CHARACTERS) {
        let construct: &str = if text[index..].starts_with('\t') {
            "tab characters"
        } else {
            "byte order marks after the start of the document"
        };
        return Err(error_at(
            text,
            index,
            ConfigErrorKind::Unsupported,
            construct.to_owned(),
        ));
    }
    if let Some(index) = line_index(text, |line| {
        line.starts_with(DIRECTIVE_INDICATOR)
            || line
                .split('\r')
                .skip(1)
                .any(|part| part.starts_with(DIRECTIVE_INDICATOR))
    }) {
        return Err(error_at(
            text,
            index,
            ConfigErrorKind::Unsupported,
            "%YAML and %TAG directives".to_owned(),
        ));
    }
    if starts_with_document_end(text) {
        let index = line_index(text, |line| !is_blank_or_comment(line)).unwrap_or(0);
        return Err(error_at(
            text,
            index,
            ConfigErrorKind::Syntax,
            "expected the node content, but found a document end marker".to_owned(),
        ));
    }
    Ok(())
}
