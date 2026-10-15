//! Quoted and unquoted relation name parts and their invalidation keys.

use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::ddl_effects::_helpers::matching::skip_whitespace;
use crate::ddl_effects::constants::QUOTED_IDENTIFIER_MIN_LENGTH;

/// Which characters an unquoted name part may contain.
#[derive(Clone, Copy)]
pub(crate) enum UnquotedPart {
    /// SQL text: starts with a letter, digit or `_`, then may also contain `$`.
    Statement,
    /// Qualified names from callers: letters, digits, `_`, `$` and `-`.
    Loose,
}

/// A qualified name: where it ends and its last part.
pub(crate) struct QualifiedName<'a> {
    pub(crate) end: usize,
    pub(crate) last_part: &'a str,
}

/// The end of the text after `open` up to and including the next `close`.
fn closed_by(text: &str, open: usize, close: u8) -> Option<usize> {
    let rest: &[u8] = text.as_bytes().get(open + 1..)?;
    rest.iter()
        .position(|byte| *byte == close)
        .map(|offset| open + offset + 2)
}

/// The end of a double-quoted part whose doubled quotes are escapes.
fn double_quoted(text: &str, open: usize) -> Option<usize> {
    let bytes: &[u8] = text.as_bytes();
    let mut position: usize = open + 1;
    loop {
        match bytes.get(position) {
            None => return None,
            Some(b'"') if bytes.get(position + 1) == Some(&b'"') => position += 2,
            Some(b'"') => return Some(position + 1),
            Some(_) => position += 1,
        }
    }
}

fn unquoted(text: &str, start: usize, kind: UnquotedPart) -> Option<usize> {
    let bytes: &[u8] = text.as_bytes();
    let first_allowed = |byte: u8| match kind {
        UnquotedPart::Statement => byte.is_ascii_alphanumeric() || byte == b'_',
        UnquotedPart::Loose => byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$' | b'-'),
    };
    let next_allowed = |byte: u8| match kind {
        UnquotedPart::Statement => byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$'),
        UnquotedPart::Loose => first_allowed(byte),
    };
    if !first_allowed(*bytes.get(start)?) {
        return None;
    }
    let length: usize = bytes[start + 1..]
        .iter()
        .take_while(|byte| next_allowed(**byte))
        .count();
    Some(start + 1 + length)
}

/// The end of one name part starting at `start`.
pub(crate) fn name_part(text: &str, start: usize, kind: UnquotedPart) -> Option<usize> {
    match text.as_bytes().get(start)? {
        b'"' => double_quoted(text, start),
        b'`' => closed_by(text, start, b'`'),
        b'[' => closed_by(text, start, b']'),
        _ => unquoted(text, start, kind),
    }
}

/// One or more parts separated by dots with optional whitespace around them.
pub(crate) fn qualified_name(
    text: &str,
    start: usize,
    kind: UnquotedPart,
) -> Option<QualifiedName<'_>> {
    let mut part_start: usize = start;
    let mut end: usize = name_part(text, start, kind)?;
    loop {
        let dot: usize = skip_whitespace(text, end);
        if text.as_bytes().get(dot) != Some(&b'.') {
            break;
        }
        let next_start: usize = skip_whitespace(text, dot + 1);
        let Some(next_end) = name_part(text, next_start, kind) else {
            break;
        };
        part_start = next_start;
        end = next_end;
    }
    Some(QualifiedName {
        end,
        last_part: &text[part_start..end],
    })
}

/// A part without its surrounding identifier quotes, unescaping doubled double quotes.
fn strip_identifier_quotes(part: &str) -> String {
    let bytes: &[u8] = part.as_bytes();
    if bytes.len() < QUOTED_IDENTIFIER_MIN_LENGTH {
        return part.to_owned();
    }
    let inner = || &part[1..part.len() - 1];
    match (bytes[0], bytes[bytes.len() - 1]) {
        (b'"', b'"') => inner().replace("\"\"", "\""),
        (b'`', b'`') | (b'[', b']') => inner().to_owned(),
        _ => part.to_owned(),
    }
}

/// The invalidation key of one unquoted or quoted unqualified relation name.
pub(crate) fn name_key(name: &str) -> String {
    python_casefold(&strip_identifier_quotes(name))
}

/// The key of a qualified name's last part; a backticked part keys its last dotted segment.
pub(crate) fn part_name_key(part: &str) -> String {
    if !part.starts_with('`') {
        return name_key(part);
    }
    let stripped: String = strip_identifier_quotes(part);
    let segment: &str = stripped.rsplit('.').next().unwrap_or_default();
    python_casefold(segment)
}
