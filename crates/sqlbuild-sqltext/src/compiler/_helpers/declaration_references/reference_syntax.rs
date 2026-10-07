//! Python's `@enum("name").MEMBER` and `@const("name")` patterns at one reference start.

use crate::compiler::models::DeclarationReferenceKind;

/// One matched reference: kind, name, member and the byte offset after it.
pub(crate) struct MatchedReference<'sql> {
    pub(crate) kind: DeclarationReferenceKind,
    pub(crate) name: &'sql str,
    pub(crate) member: Option<&'sql str>,
    pub(crate) end: usize,
}

/// Why a reference start cannot be matched natively.
pub(crate) enum ReferenceSyntax<'sql> {
    /// `@enum`/`@const` followed by a word character: not a reference, keep scanning.
    NotReference,
    Matched(MatchedReference<'sql>),
    /// Malformed or Unicode-dependent text: Python raises or decides.
    Deferred,
}

/// Match Python's `@(enum|const)\b` start and the full reference pattern at `start`.
pub(crate) fn match_reference(sql: &str, start: usize) -> ReferenceSyntax<'_> {
    let bytes: &[u8] = sql.as_bytes();
    let (kind, keyword_end) = if bytes[start..].starts_with(b"@enum") {
        (DeclarationReferenceKind::Enum, start + 5)
    } else if bytes[start..].starts_with(b"@const") {
        (DeclarationReferenceKind::Constant, start + 6)
    } else {
        return ReferenceSyntax::NotReference;
    };
    match bytes.get(keyword_end) {
        Some(byte) if !byte.is_ascii() => return ReferenceSyntax::Deferred,
        Some(byte) if is_word(*byte) => return ReferenceSyntax::NotReference,
        _ => {}
    }
    let Some(matched) = match_arguments(sql, kind, keyword_end) else {
        return ReferenceSyntax::Deferred;
    };
    ReferenceSyntax::Matched(matched)
}

fn match_arguments(
    sql: &str,
    kind: DeclarationReferenceKind,
    keyword_end: usize,
) -> Option<MatchedReference<'_>> {
    let bytes: &[u8] = sql.as_bytes();
    let mut index: usize = consume(bytes, skip_whitespace(bytes, keyword_end)?, b'(')?;
    index = skip_whitespace(bytes, index)?;
    let quote: u8 = *bytes
        .get(index)
        .filter(|byte| matches!(byte, b'\'' | b'"'))?;
    let name_start: usize = index + 1;
    let name_end: usize = identifier_end(bytes, name_start)?;
    index = consume(bytes, name_end, quote)?;
    index = consume(bytes, skip_whitespace(bytes, index)?, b')')?;
    let mut member: Option<&str> = None;
    if matches!(kind, DeclarationReferenceKind::Enum) {
        index = consume(bytes, skip_whitespace(bytes, index)?, b'.')?;
        let member_start: usize = skip_whitespace(bytes, index)?;
        index = identifier_end(bytes, member_start)?;
        member = Some(&sql[member_start..index]);
    }
    Some(MatchedReference {
        kind,
        name: &sql[name_start..name_end],
        member,
        end: index,
    })
}

/// Python's `\s*` over ASCII; a non-ASCII byte may be Unicode whitespace, so it defers.
fn skip_whitespace(bytes: &[u8], mut index: usize) -> Option<usize> {
    while let Some(byte) = bytes.get(index) {
        if !byte.is_ascii() {
            return None;
        }
        if !matches!(
            byte,
            b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c | 0x1c..=0x1f
        ) {
            break;
        }
        index += 1;
    }
    Some(index)
}

fn consume(bytes: &[u8], index: usize, expected: u8) -> Option<usize> {
    (bytes.get(index) == Some(&expected)).then_some(index + 1)
}

/// The end of `[A-Za-z_][A-Za-z0-9_]*` starting at `start`.
fn identifier_end(bytes: &[u8], start: usize) -> Option<usize> {
    let first: u8 = *bytes.get(start)?;
    if !(first.is_ascii_alphabetic() || first == b'_') {
        return None;
    }
    let mut end: usize = start + 1;
    while bytes.get(end).copied().is_some_and(is_word) {
        end += 1;
    }
    Some(end)
}

fn is_word(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}
