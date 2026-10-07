//! Python's `_find_next_reference_start` walk over quoted text and comments.

use crate::compiler::_helpers::declaration_references::reference_syntax::{
    ReferenceSyntax, match_reference,
};
use crate::compiler::models::DeclarationReference;

const SPECIAL_BYTES: &[u8] = b"'\"`$@/-";

/// Every `@enum`/`@const` reference in `sql` with code-point offsets, or None when Python decides.
pub(crate) fn scan_references(sql: &str) -> Option<Vec<DeclarationReference>> {
    let mut references: Vec<DeclarationReference> = Vec::new();
    let mut offsets: CharOffsets = CharOffsets::default();
    let mut cursor: usize = 0;
    while cursor < sql.len() {
        let Some(start) = next_reference_start(sql, cursor)? else {
            break;
        };
        let ReferenceSyntax::Matched(matched) = match_reference(sql, start) else {
            return None;
        };
        let start_char: usize = offsets.advance(sql, start);
        let end_char: usize = offsets.advance(sql, matched.end);
        references.push(DeclarationReference {
            kind: matched.kind,
            name: matched.name.to_owned(),
            member: matched.member.map(str::to_owned),
            start: start_char,
            end: end_char,
        });
        cursor = matched.end;
    }
    Some(references)
}

/// The next reference start at or after `start`; the outer None means Python decides.
fn next_reference_start(sql: &str, start: usize) -> Option<Option<usize>> {
    let rest: &str = &sql[start..];
    if !rest.contains("@enum") && !rest.contains("@const") {
        return Some(None);
    }
    let bytes: &[u8] = sql.as_bytes();
    let mut index: usize = start;
    while let Some(offset) = bytes[index..]
        .iter()
        .position(|byte| SPECIAL_BYTES.contains(byte))
    {
        index += offset;
        index = match bytes[index] {
            b'\'' | b'"' => quoted_end(bytes, index, true)?,
            b'`' => quoted_end(bytes, index, false)?,
            b'$' => dollar_end(bytes, index)?.unwrap_or(index + 1),
            b'-' if bytes.get(index + 1) == Some(&b'-') => bytes[index..]
                .iter()
                .position(|byte| *byte == b'\n')
                .map_or(bytes.len(), |newline| index + newline + 1),
            b'/' if bytes.get(index + 1) == Some(&b'*') => {
                index + 2 + find(&bytes[index + 2..], b"*/")? + 2
            }
            b'@' => match match_reference(sql, index) {
                ReferenceSyntax::NotReference => index + 1,
                ReferenceSyntax::Matched(_) | ReferenceSyntax::Deferred => {
                    return Some(Some(index));
                }
            },
            _ => index + 1,
        };
    }
    Some(None)
}

/// Python's `quoted_text_end_impl` for `'`, `"` (doubled quotes escape) and backticks.
fn quoted_end(bytes: &[u8], start: usize, doubled_escapes: bool) -> Option<usize> {
    let quote: u8 = bytes[start];
    let mut index: usize = start + 1;
    loop {
        index += bytes[index..].iter().position(|byte| *byte == quote)?;
        if doubled_escapes && bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Some(index + 1);
    }
}

/// Python's `_dollar_quoted_text_end`: Some(None) when `$` opens no literal.
fn dollar_end(bytes: &[u8], start: usize) -> Option<Option<usize>> {
    if start
        .checked_sub(1)
        .is_some_and(|previous| continues_dollar_word(bytes[previous]))
    {
        return Some(None);
    }
    let tag_end: usize = bytes[start + 1..]
        .iter()
        .position(|byte| !(byte.is_ascii_alphanumeric() || *byte == b'_'))
        .map_or(bytes.len(), |offset| start + 1 + offset);
    if bytes.get(tag_end) != Some(&b'$') || bytes.get(start + 1).is_some_and(u8::is_ascii_digit) {
        return Some(None);
    }
    let delimiter: &[u8] = &bytes[start..=tag_end];
    let closing: usize = find(&bytes[tag_end + 1..], delimiter)?;
    Some(Some(tag_end + 1 + closing + delimiter.len()))
}

fn continues_dollar_word(byte: u8) -> bool {
    !byte.is_ascii() || byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$')
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

/// Converts increasing byte offsets into Python code-point offsets.
#[derive(Default)]
struct CharOffsets {
    byte: usize,
    char: usize,
}

impl CharOffsets {
    fn advance(&mut self, sql: &str, byte: usize) -> usize {
        self.char += sql[self.byte..byte].chars().count();
        self.byte = byte;
        self.char
    }
}
