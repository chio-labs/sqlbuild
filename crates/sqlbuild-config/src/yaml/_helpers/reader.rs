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

/// Reject what PyYAML's reader rejects, and defer characters PyYAML and LibYAML read differently.
pub(crate) fn check_characters(text: &str) -> Result<(), ConfigError> {
    if let Some(character) = text.chars().find(|character| !is_printable(*character)) {
        return Err(ConfigError::new(
            ConfigErrorKind::Syntax,
            format!("unacceptable character {:#x}", u32::from(character)),
        ));
    }
    if text.contains(PYTHON_ONLY_LINE_BREAKS) {
        return Err(ConfigError::new(
            ConfigErrorKind::Unsupported,
            "NEL, LINE SEPARATOR and PARAGRAPH SEPARATOR are YAML 1.1 line breaks",
        ));
    }
    if text.contains(LOADER_DEPENDENT_CHARACTERS) {
        return Err(ConfigError::new(
            ConfigErrorKind::Unsupported,
            "tabs and inner byte order marks are read differently by PyYAML and LibYAML",
        ));
    }
    let directive = text.starts_with(DIRECTIVE_INDICATOR)
        || text
            .split(['\n', '\r'])
            .any(|line| line.starts_with(DIRECTIVE_INDICATOR));
    if directive {
        return Err(ConfigError::new(
            ConfigErrorKind::Unsupported,
            "directives are left to Python",
        ));
    }
    if starts_with_document_end(text) {
        return Err(ConfigError::new(
            ConfigErrorKind::Syntax,
            "expected the node content, but found a document end marker",
        ));
    }
    Ok(())
}
