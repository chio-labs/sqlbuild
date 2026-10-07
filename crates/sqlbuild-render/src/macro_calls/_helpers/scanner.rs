//! Byte offset port of the Python macro call scanner; unsure or rejected text defers to Python.

use sqlbuild_core::text::main::is_python_alnum::is_python_alnum;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::models::PythonText;

use crate::macro_calls::models::ScanDeferral;

const TYPED_REFERENCE_NAMES: [&str; 3] = ["__ref", "__source", "__seed"];

/// One call found by the scanner, in byte offsets of the scanned text.
pub(crate) struct ScannedCall {
    pub(crate) start: usize,
    pub(crate) open: usize,
    pub(crate) close: usize,
    pub(crate) name: String,
}

/// Return every top-level call of `text` in order.
pub(crate) fn top_level_calls(
    python: PythonText,
    text: &str,
) -> Result<Vec<ScannedCall>, ScanDeferral> {
    let mut calls: Vec<ScannedCall> = Vec::new();
    let mut cursor = 0;
    while cursor < text.len() {
        let Some(start) = next_macro_start(python, text, cursor)? else {
            break;
        };
        let call = call_at(python, text, start)?;
        cursor = call.close + 1;
        calls.push(call);
    }
    Ok(calls)
}

/// Return the names of every call nested in `args`, depth first, with repeats.
pub(crate) fn nested_names(python: PythonText, args: &str) -> Result<Vec<String>, ScanDeferral> {
    let mut names: Vec<String> = Vec::new();
    for call in top_level_calls(python, args)? {
        let inner = nested_names(python, &args[call.open + 1..call.close])?;
        names.push(call.name);
        names.extend(inner);
    }
    Ok(names)
}

/// Whether call arguments mention a typed reference function name anywhere.
pub(crate) fn mentions_typed_reference(args: &str) -> bool {
    TYPED_REFERENCE_NAMES.iter().any(|name| args.contains(name))
}

fn call_at(python: PythonText, text: &str, start: usize) -> Result<ScannedCall, ScanDeferral> {
    let name_end = identifier_end(python, text, start + 1);
    let open = skip_whitespace(text, name_end);
    if text.as_bytes().get(open) != Some(&b'(') {
        return Err(ScanDeferral);
    }
    let close = matching_paren(text.as_bytes(), open)?;
    Ok(ScannedCall {
        start,
        open,
        close,
        name: text[start + 1..name_end].to_owned(),
    })
}

fn next_macro_start(
    python: PythonText,
    text: &str,
    from: usize,
) -> Result<Option<usize>, ScanDeferral> {
    let bytes = text.as_bytes();
    let mut index = from;
    while index < bytes.len() {
        match bytes[index] {
            b'\'' | b'"' | b'`' => index = quote_end(bytes, index)?,
            b'$' => index = dollar_quote_end(bytes, index)?.unwrap_or(index + 1),
            b'-' if bytes.get(index + 1) == Some(&b'-') => index = line_comment_end(bytes, index),
            b'/' if bytes.get(index + 1) == Some(&b'*') => index = block_comment_end(bytes, index)?,
            b'@' => {
                if macro_call_starts_at(python, text, index)? {
                    return Ok(Some(index));
                }
                index += 1;
            }
            _ => index += 1,
        }
    }
    Ok(None)
}

fn macro_call_starts_at(python: PythonText, text: &str, at: usize) -> Result<bool, ScanDeferral> {
    let Some(first) = char_at(text, at + 1) else {
        return Ok(false);
    };
    if !first.is_ascii() {
        return Err(ScanDeferral);
    }
    if !(first.is_ascii_alphabetic() || first == '_') {
        return Ok(false);
    }
    let mut cursor = at + 2;
    while let Some(character) = char_at(text, cursor) {
        if !is_identifier_continue(python, character) {
            break;
        }
        cursor = skip_whitespace(text, cursor + character.len_utf8());
    }
    Ok(text.as_bytes().get(cursor) == Some(&b'('))
}

fn identifier_end(python: PythonText, text: &str, from: usize) -> usize {
    let mut cursor = from;
    while let Some(character) = char_at(text, cursor) {
        if !is_identifier_continue(python, character) {
            break;
        }
        cursor += character.len_utf8();
    }
    cursor
}

fn is_identifier_continue(python: PythonText, character: char) -> bool {
    character == '_' || is_python_alnum(python, character)
}

fn skip_whitespace(text: &str, from: usize) -> usize {
    let mut cursor = from;
    while let Some(character) = char_at(text, cursor) {
        if !is_python_space(character) {
            break;
        }
        cursor += character.len_utf8();
    }
    cursor
}

fn char_at(text: &str, index: usize) -> Option<char> {
    text.get(index..).and_then(|rest| rest.chars().next())
}

fn matching_paren(bytes: &[u8], open: usize) -> Result<usize, ScanDeferral> {
    let mut depth = 1usize;
    let mut index = open + 1;
    while index < bytes.len() {
        match bytes[index] {
            b'\'' | b'"' | b'`' => {
                index = quote_end(bytes, index)?;
                continue;
            }
            b'$' => {
                if let Some(end) = dollar_quote_end(bytes, index)? {
                    index = end;
                    continue;
                }
            }
            b'-' if bytes.get(index + 1) == Some(&b'-') => {
                index = line_comment_end(bytes, index);
                continue;
            }
            b'/' if bytes.get(index + 1) == Some(&b'*') => {
                index = block_comment_end(bytes, index)?;
                continue;
            }
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => {}
        }
        index += 1;
    }
    Err(ScanDeferral)
}

fn quote_end(bytes: &[u8], start: usize) -> Result<usize, ScanDeferral> {
    let quote = bytes[start];
    let doubled_escapes = quote == b'\'' || quote == b'"';
    let mut index = start + 1;
    loop {
        let offset = bytes[index.min(bytes.len())..]
            .iter()
            .position(|byte| *byte == quote)
            .ok_or(ScanDeferral)?;
        index += offset;
        if doubled_escapes && bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Ok(index + 1);
    }
}

fn dollar_quote_end(bytes: &[u8], start: usize) -> Result<Option<usize>, ScanDeferral> {
    if start
        .checked_sub(1)
        .is_some_and(|previous| continues_dollar_word(bytes[previous]))
    {
        return Ok(None);
    }
    let tag_end = bytes[start + 1..]
        .iter()
        .position(|byte| !(byte.is_ascii_alphanumeric() || *byte == b'_'))
        .map_or(bytes.len(), |offset| start + 1 + offset);
    let tag = &bytes[start + 1..tag_end];
    if bytes.get(tag_end) != Some(&b'$') || tag.first().is_some_and(u8::is_ascii_digit) {
        return Ok(None);
    }
    let delimiter = &bytes[start..=tag_end];
    bytes[tag_end + 1..]
        .windows(delimiter.len())
        .position(|window| window == delimiter)
        .map(|offset| Some(tag_end + 1 + offset + delimiter.len()))
        .ok_or(ScanDeferral)
}

fn continues_dollar_word(byte: u8) -> bool {
    !byte.is_ascii() || byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$')
}

fn line_comment_end(bytes: &[u8], start: usize) -> usize {
    bytes[start..]
        .iter()
        .position(|byte| *byte == b'\n')
        .map_or(bytes.len(), |offset| start + offset + 1)
}

fn block_comment_end(bytes: &[u8], start: usize) -> Result<usize, ScanDeferral> {
    bytes[start + 2..]
        .windows(2)
        .position(|pair| pair == b"*/")
        .map(|offset| start + 2 + offset + 2)
        .ok_or(ScanDeferral)
}
