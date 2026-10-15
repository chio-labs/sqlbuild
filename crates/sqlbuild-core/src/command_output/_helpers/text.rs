//! `strip_ansi`, `str.splitlines(keepends=True)` and `chunk_text` over `surrogatepass` bytes.

use crate::command_output::constants::{
    ASCII_LINE_BREAKS, BELL, CSI_FINAL, CSI_INTERMEDIATES, CSI_INTRODUCER, CSI_PARAMETERS,
    ESCAPABLE_SURROGATES, ESCAPE, NEXT_LINE, OSC_INTRODUCER, STRING_TERMINATOR, SURROGATE_LEAD,
    SURROGATE_SECOND, UNICODE_LINE_BREAKS, UTF8_CONTINUATION_MASK, UTF8_CONTINUATION_TAG,
};
use crate::command_output::errors::UnencodableText;

/// Byte length of the code point whose UTF-8 encoding starts with `lead`.
fn sequence_length(lead: u8) -> usize {
    match lead {
        0x00..=0x7f => 1,
        0xc0..=0xdf => 2,
        0xe0..=0xef => 3,
        _ => 4,
    }
}

fn is_continuation(byte: u8) -> bool {
    byte & UTF8_CONTINUATION_MASK == UTF8_CONTINUATION_TAG
}

/// The surrogate code point encoded at `index`, if the bytes there encode one.
fn surrogate_at(text: &[u8], index: usize) -> Option<u32> {
    let (Some(&lead), Some(&second), Some(&third)) =
        (text.get(index), text.get(index + 1), text.get(index + 2))
    else {
        return None;
    };
    if lead != SURROGATE_LEAD || !SURROGATE_SECOND.contains(&second) {
        return None;
    }
    Some(0xd000 | (u32::from(second & 0x3f) << 6) | u32::from(third & 0x3f))
}

/// The first lone surrogate in `text`, which strict UTF-8 cannot encode.
pub(crate) fn first_surrogate(text: &[u8]) -> Option<UnencodableText> {
    let found = text
        .windows(2)
        .position(|pair| pair[0] == SURROGATE_LEAD && SURROGATE_SECOND.contains(&pair[1]))?;
    let code_point = surrogate_at(text, found)?;
    let position = text[..found]
        .iter()
        .filter(|byte| !is_continuation(**byte))
        .count();
    Some(UnencodableText {
        position,
        code_point,
    })
}

/// `len(text.encode("utf-8"))`, failing on a lone surrogate.
pub(crate) fn strict_utf8_length(text: &[u8]) -> Result<usize, UnencodableText> {
    match first_surrogate(text) {
        Some(error) => Err(error),
        None => Ok(text.len()),
    }
}

/// End of an OSC sequence starting at `start`, terminated by BEL or `ESC \`.
fn osc_end(text: &[u8], start: usize) -> Option<usize> {
    let mut index = start + 2;
    while let Some(&byte) = text.get(index) {
        if byte == BELL {
            return Some(index + 1);
        }
        if byte == ESCAPE {
            return (text.get(index + 1) == Some(&STRING_TERMINATOR)).then_some(index + 2);
        }
        index += 1;
    }
    None
}

/// End of a CSI sequence starting at `start`: parameters, intermediates, one final byte.
fn csi_end(text: &[u8], start: usize) -> Option<usize> {
    let mut index = start + 2;
    while text
        .get(index)
        .is_some_and(|byte| CSI_PARAMETERS.contains(byte))
    {
        index += 1;
    }
    while text
        .get(index)
        .is_some_and(|byte| CSI_INTERMEDIATES.contains(byte))
    {
        index += 1;
    }
    text.get(index)
        .filter(|byte| CSI_FINAL.contains(byte))
        .map(|_| index + 1)
}

/// `_ANSI_ESCAPE.sub("", text)`: drop OSC and CSI terminal control sequences.
pub(crate) fn strip_ansi(text: &[u8]) -> Vec<u8> {
    let mut plain: Vec<u8> = Vec::with_capacity(text.len());
    let mut index: usize = 0;
    while index < text.len() {
        let end = match (text[index], text.get(index + 1)) {
            (ESCAPE, Some(&OSC_INTRODUCER)) => osc_end(text, index),
            (ESCAPE, Some(&CSI_INTRODUCER)) => csi_end(text, index),
            _ => None,
        };
        match end {
            Some(end) => index = end,
            None => {
                plain.push(text[index]);
                index += 1;
            }
        }
    }
    plain
}

/// Length of the line boundary at `index`, if one starts there.
fn line_break_length(text: &[u8], index: usize) -> Option<usize> {
    let byte = text[index];
    if byte == b'\r' && text.get(index + 1) == Some(&b'\n') {
        return Some(2);
    }
    if ASCII_LINE_BREAKS.contains(&byte) {
        return Some(1);
    }
    if text[index..].starts_with(&NEXT_LINE) {
        return Some(NEXT_LINE.len());
    }
    UNICODE_LINE_BREAKS
        .iter()
        .find(|boundary| text[index..].starts_with(boundary.as_slice()))
        .map(|boundary| boundary.len())
}

/// `text.splitlines(keepends=True)`.
pub(crate) fn split_lines(text: &[u8]) -> Vec<&[u8]> {
    let mut lines: Vec<&[u8]> = Vec::new();
    let mut start: usize = 0;
    let mut index: usize = 0;
    while index < text.len() {
        match line_break_length(text, index) {
            Some(length) => {
                index += length;
                lines.push(&text[start..index]);
                start = index;
            }
            None => index += sequence_length(text[index]),
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

/// `_chunk_utf8`: greedy chunks ending at the last code point boundary within `max_bytes`.
fn chunk_utf8(text: &[u8], max_bytes: i64) -> Vec<Vec<u8>> {
    let mut chunks: Vec<Vec<u8>> = Vec::new();
    let total = text.len();
    let mut start: usize = 0;
    while start < total {
        let limit = usize::try_from(max_bytes).unwrap_or(0);
        let mut end = start.saturating_add(limit);
        if end >= total {
            end = total;
        } else {
            while end > start && is_continuation(text[end]) {
                end -= 1;
            }
            if end <= start {
                end = start + 1;
                while end < total && is_continuation(text[end]) {
                    end += 1;
                }
            }
        }
        chunks.push(text[start..end].to_vec());
        start = end;
    }
    if chunks.is_empty() {
        chunks.push(Vec::new());
    }
    chunks
}

/// `len(character.encode("utf-8", "surrogateescape"))` of the code point at `index`.
fn escaped_length(text: &[u8], index: usize, position: usize) -> Result<usize, UnencodableText> {
    match surrogate_at(text, index) {
        Some(code_point) if ESCAPABLE_SURROGATES.contains(&code_point) => Ok(1),
        Some(code_point) => Err(UnencodableText {
            position,
            code_point,
        }),
        None => Ok(sequence_length(text[index])),
    }
}

/// `_chunk_text_by_character`: text with surrogates, each escaped surrogate one byte.
fn chunk_by_character(text: &[u8], max_bytes: i64) -> Result<Vec<Vec<u8>>, UnencodableText> {
    let mut chunks: Vec<Vec<u8>> = Vec::new();
    let mut current: Vec<u8> = Vec::new();
    let mut current_bytes: i64 = 0;
    let mut index: usize = 0;
    let mut position: usize = 0;
    while index < text.len() {
        let length = sequence_length(text[index]);
        let encoded = i64::try_from(escaped_length(text, index, position)?).unwrap_or(i64::MAX);
        if !current.is_empty() && current_bytes + encoded > max_bytes {
            chunks.push(std::mem::take(&mut current));
            current_bytes = 0;
        }
        current.extend_from_slice(&text[index..index + length]);
        current_bytes += encoded;
        index += length;
        position += 1;
    }
    if !current.is_empty() || chunks.is_empty() {
        chunks.push(current);
    }
    Ok(chunks)
}

/// `chunk_text`: split text deterministically without splitting code points.
pub(crate) fn chunk_text(text: &[u8], max_bytes: i64) -> Result<Vec<Vec<u8>>, UnencodableText> {
    if text.is_ascii() && max_bytes > 0 {
        return Ok(chunk_utf8(text, max_bytes));
    }
    if first_surrogate(text).is_some() {
        return chunk_by_character(text, max_bytes);
    }
    if i64::try_from(text.len()).unwrap_or(i64::MAX) <= max_bytes {
        return Ok(vec![text.to_vec()]);
    }
    Ok(chunk_utf8(text, max_bytes))
}
