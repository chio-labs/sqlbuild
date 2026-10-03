//! Exact native equivalent of the possessive Python `MODEL(...)` header regular expression.

/// Code-point offsets of one matched header: header start, header end, and SQL start.
pub(crate) type HeaderMatchOffsets = (usize, usize, usize);

const MODEL_KEYWORD: &[u8] = b"MODEL";

pub(crate) fn match_one(text: &str) -> Option<HeaderMatchOffsets> {
    let bytes = text.as_bytes();
    let mut index = skip_whitespace(text, 0);
    if !bytes[index..].starts_with(MODEL_KEYWORD) {
        return None;
    }
    index = skip_whitespace(text, index + MODEL_KEYWORD.len());
    if bytes.get(index) != Some(&b'(') {
        return None;
    }
    let header_start = index + 1;
    let header_end = scan_header_body(text, header_start);
    if bytes.get(header_end) != Some(&b')') {
        return None;
    }
    index = skip_whitespace(text, header_end + 1);
    if bytes.get(index) != Some(&b';') {
        return None;
    }
    let sql_start = skip_whitespace(text, index + 1);
    Some(code_point_offsets(
        text,
        header_start,
        header_end,
        sql_start,
    ))
}

/// Consume the possessive header body and return the byte offset where it stops.
fn scan_header_body(text: &str, start: usize) -> usize {
    let bytes = text.as_bytes();
    let mut index = start;
    while let Some(&byte) = bytes.get(index) {
        index = match byte {
            b'"' | b'\'' => quoted_string_end(text, index, byte)
                .unwrap_or_else(|| unclosed_quote_end(text, index)),
            b')' => {
                let after = skip_whitespace(text, index + 1);
                if bytes.get(after) == Some(&b';') {
                    return index;
                }
                index + 1
            }
            b'\\' => match escape_end(text, index) {
                Some(end) => end,
                None => return index,
            },
            _ => index + 1,
        };
    }
    index
}

/// `"(?:[^"\\]|\\.)*+"`: the closing quote's end, or `None` when the string never closes.
fn quoted_string_end(text: &str, open: usize, quote: u8) -> Option<usize> {
    let bytes = text.as_bytes();
    let mut index = open + 1;
    while let Some(&byte) = bytes.get(index) {
        if byte == quote {
            return Some(index + 1);
        }
        if byte == b'\\' {
            index = escape_end(text, index)?;
        } else {
            index += 1;
        }
    }
    None
}

/// `["'](?:[^\\)]|\\.)*+`: an unclosed quote runs to the next `)` or unescapable backslash.
fn unclosed_quote_end(text: &str, open: usize) -> usize {
    let bytes = text.as_bytes();
    let mut index = open + 1;
    while let Some(&byte) = bytes.get(index) {
        match byte {
            b')' => return index,
            b'\\' => match escape_end(text, index) {
                Some(end) => index = end,
                None => return index,
            },
            _ => index += 1,
        }
    }
    index
}

/// `\\.` with DOTALL: a backslash plus one following code point, if any.
fn escape_end(text: &str, backslash: usize) -> Option<usize> {
    text[backslash + 1..]
        .chars()
        .next()
        .map(|escaped| backslash + 1 + escaped.len_utf8())
}

fn skip_whitespace(text: &str, start: usize) -> usize {
    let mut index = start;
    for character in text[start..].chars() {
        if !is_python_whitespace(character) {
            break;
        }
        index += character.len_utf8();
    }
    index
}

/// Python's `str.isspace()`, which `\s` uses for `str` patterns.
fn is_python_whitespace(character: char) -> bool {
    matches!(
        character,
        '\t'..='\r'
            | '\u{1c}'..='\u{20}'
            | '\u{85}'
            | '\u{a0}'
            | '\u{1680}'
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}'
            | '\u{2029}'
            | '\u{202f}'
            | '\u{205f}'
            | '\u{3000}'
    )
}

fn code_point_offsets(
    text: &str,
    header_start: usize,
    header_end: usize,
    sql_start: usize,
) -> HeaderMatchOffsets {
    if text.is_ascii() {
        return (header_start, header_end, sql_start);
    }
    let header_start_chars = text[..header_start].chars().count();
    let header_end_chars = header_start_chars + text[header_start..header_end].chars().count();
    let sql_start_chars = header_end_chars + text[header_end..sql_start].chars().count();
    (header_start_chars, header_end_chars, sql_start_chars)
}
