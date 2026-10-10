//! Byte offset port of the Python macro call scanner, with the errors Python's scan raises.

use sqlbuild_core::text::main::is_python_alnum::is_python_alnum;
use sqlbuild_core::text::main::is_python_alpha::is_python_alpha;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::models::PythonText;

use crate::macro_calls::models::ScanError;

const TYPED_REFERENCE_NAMES: [&str; 3] = ["__ref", "__source", "__seed"];

/// One call found by the scanner, in byte offsets of the scanned text.
pub(crate) struct ScannedCall {
    pub(crate) start: usize,
    pub(crate) open: usize,
    pub(crate) close: usize,
    pub(crate) name: String,
}

/// Where Python's scan of the text raises: in the call starting at a byte offset, or between
/// calls.
pub(crate) struct ScannedFailure {
    pub(crate) call_start: Option<usize>,
    pub(crate) error: ScanError,
}

/// Every top-level call of `text` in order, up to the first error Python's scan raises.
pub(crate) fn top_level_calls(
    python: PythonText,
    text: &str,
) -> (Vec<ScannedCall>, Option<ScannedFailure>) {
    let mut calls: Vec<ScannedCall> = Vec::new();
    let mut cursor = 0;
    while cursor < text.len() {
        let start = match next_macro_start(python, text, cursor) {
            Ok(Some(start)) => start,
            Ok(None) => break,
            Err(error) => {
                let failure = ScannedFailure {
                    call_start: None,
                    error,
                };
                return (calls, Some(failure));
            }
        };
        match call_at(python, text, start) {
            Ok(call) => {
                cursor = call.close + 1;
                calls.push(call);
            }
            Err(error) => {
                let failure = ScannedFailure {
                    call_start: Some(start),
                    error,
                };
                return (calls, Some(failure));
            }
        }
    }
    (calls, None)
}

/// Names of every call nested in `args` in source order, in one pass without recursion.
pub(crate) fn nested_names(python: PythonText, args: &str) -> Result<Vec<String>, ScanError> {
    let bytes: &[u8] = args.as_bytes();
    let mut names: Vec<String> = Vec::new();
    let mut open_call_depths: Vec<usize> = Vec::new();
    let mut depth: usize = 0;
    let mut index: usize = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'\'' | b'"' | b'`' => index = quote_end(bytes, index)?,
            b'$' => index = dollar_quote_end(bytes, index)?.unwrap_or(index + 1),
            b'-' if bytes.get(index + 1) == Some(&b'-') => index = line_comment_end(bytes, index),
            b'/' if bytes.get(index + 1) == Some(&b'*') => index = block_comment_end(bytes, index)?,
            b'@' if macro_call_starts_at(python, args, index) => {
                let (name, open) = call_header(python, args, index)?;
                names.push(name);
                depth += 1;
                open_call_depths.push(depth);
                index = open + 1;
            }
            b'(' => {
                depth += 1;
                index += 1;
            }
            b')' => {
                if open_call_depths.last() == Some(&depth) {
                    let _ = open_call_depths.pop();
                }
                depth = depth.checked_sub(1).ok_or(ScanError::UnclosedParenthesis)?;
                index += 1;
            }
            _ => index += 1,
        }
    }
    if open_call_depths.is_empty() {
        Ok(names)
    } else {
        Err(ScanError::UnclosedParenthesis)
    }
}

/// Whether call arguments mention a typed reference function name anywhere.
pub(crate) fn mentions_typed_reference(args: &str) -> bool {
    TYPED_REFERENCE_NAMES.iter().any(|name| args.contains(name))
}

fn call_at(python: PythonText, text: &str, start: usize) -> Result<ScannedCall, ScanError> {
    let (name, open) = call_header(python, text, start)?;
    let close = matching_paren(text.as_bytes(), open)?;
    Ok(ScannedCall {
        start,
        open,
        close,
        name,
    })
}

fn call_header(python: PythonText, text: &str, start: usize) -> Result<(String, usize), ScanError> {
    let name_end = identifier_end(python, text, start + 1);
    let open = skip_whitespace(text, name_end);
    if text.as_bytes().get(open) != Some(&b'(') {
        return Err(ScanError::MissingParenthesis);
    }
    Ok((text[start + 1..name_end].to_owned(), open))
}

fn next_macro_start(
    python: PythonText,
    text: &str,
    from: usize,
) -> Result<Option<usize>, ScanError> {
    let bytes = text.as_bytes();
    let mut index = from;
    while index < bytes.len() {
        match bytes[index] {
            b'\'' | b'"' | b'`' => index = quote_end(bytes, index)?,
            b'$' => index = dollar_quote_end(bytes, index)?.unwrap_or(index + 1),
            b'-' if bytes.get(index + 1) == Some(&b'-') => index = line_comment_end(bytes, index),
            b'/' if bytes.get(index + 1) == Some(&b'*') => index = block_comment_end(bytes, index)?,
            b'@' => {
                if macro_call_starts_at(python, text, index) {
                    return Ok(Some(index));
                }
                index += 1;
            }
            _ => index += 1,
        }
    }
    Ok(None)
}

fn macro_call_starts_at(python: PythonText, text: &str, at: usize) -> bool {
    let Some(first) = char_at(text, at + 1) else {
        return false;
    };
    if !(first == '_' || is_python_alpha(python, first)) {
        return false;
    }
    let mut cursor = at + 1 + first.len_utf8();
    while let Some(character) = char_at(text, cursor) {
        if !is_identifier_continue(python, character) {
            break;
        }
        cursor = skip_whitespace(text, cursor + character.len_utf8());
    }
    text.as_bytes().get(cursor) == Some(&b'(')
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

fn matching_paren(bytes: &[u8], open: usize) -> Result<usize, ScanError> {
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
    Err(ScanError::UnclosedParenthesis)
}

fn quote_end(bytes: &[u8], start: usize) -> Result<usize, ScanError> {
    let quote = bytes[start];
    let doubled_escapes = quote == b'\'' || quote == b'"';
    let mut index = start + 1;
    loop {
        let offset = bytes[index.min(bytes.len())..]
            .iter()
            .position(|byte| *byte == quote)
            .ok_or(ScanError::UnclosedQuote)?;
        index += offset;
        if doubled_escapes && bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Ok(index + 1);
    }
}

fn dollar_quote_end(bytes: &[u8], start: usize) -> Result<Option<usize>, ScanError> {
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
        .ok_or(ScanError::UnclosedQuote)
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

fn block_comment_end(bytes: &[u8], start: usize) -> Result<usize, ScanError> {
    bytes[start + 2..]
        .windows(2)
        .position(|pair| pair == b"*/")
        .map(|offset| start + 2 + offset + 2)
        .ok_or(ScanError::UnclosedComment)
}
