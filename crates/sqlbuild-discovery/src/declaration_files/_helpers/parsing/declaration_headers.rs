//! Python's `_parse_declaration_headers`: split a file into `KIND(...);` headers and parse each.

use crate::declaration_files::_helpers::checks::python_values::failure;
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::models::FailureKind;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_sqltext::compiler::main::model_header_single_parsing::parse_one;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

const DECLARATION_KINDS: [&str; 3] = ["ENUM", "CONSTANT", "SCHEMA"];

/// One parsed declaration header with its byte range in the file.
pub(crate) struct DeclarationHeader {
    pub(crate) values: Vec<(String, AuthoredValue)>,
    pub(crate) header_start: usize,
    pub(crate) header_end: usize,
    /// The tokenizer's column-key offsets, for schema column locations.
    pub(crate) column_offsets: Vec<(String, usize, usize)>,
}

/// Every `expected_kind(...)` header in `contents`, or the first failure Python raises.
pub(crate) fn declaration_headers(
    contents: &str,
    file_path: &str,
    expected_kind: &str,
) -> Result<Vec<DeclarationHeader>, ParseStop> {
    let declaration = |message: String| failure(FailureKind::Declaration, message);
    let mut headers: Vec<DeclarationHeader> = Vec::new();
    let mut cursor: usize = 0;
    while cursor < contents.len() {
        cursor = skip_whitespace(contents, cursor);
        if cursor == contents.len() {
            break;
        }
        let Some((actual_kind, open_index)) = declaration_start(contents, cursor) else {
            return Err(declaration(format!(
                "{file_path} must contain only {expected_kind}(...) declarations"
            )));
        };
        if actual_kind != expected_kind {
            return Err(declaration(format!(
                "{file_path} contains {actual_kind}(...) under the {}s root",
                expected_kind.to_ascii_lowercase()
            )));
        }
        let Some(close_index) = closing_parenthesis(contents, open_index) else {
            return Err(declaration(format!(
                "{file_path} has an unterminated declaration header"
            )));
        };
        cursor = skip_whitespace(contents, close_index + 1);
        if contents.as_bytes().get(cursor) != Some(&b';') {
            return Err(declaration(format!(
                "{expected_kind}(...) in '{file_path}' must end with ';'"
            )));
        }
        let header_start: usize = open_index + 1;
        let (values, column_offsets) = match parse_one(&contents[header_start..close_index]) {
            (_, _, Some(error)) => {
                return Err(declaration(syntax_message(
                    expected_kind,
                    file_path,
                    &error,
                )));
            }
            (Some(AuthoredValue::Map(values)), Some(offsets), None) => (values, offsets),
            _ => {
                return Err(declaration(syntax_message(
                    expected_kind,
                    file_path,
                    "Native MODEL header parser returned neither values nor an error",
                )));
            }
        };
        headers.push(DeclarationHeader {
            values,
            header_start,
            header_end: close_index,
            column_offsets,
        });
        cursor += 1;
    }
    if headers.is_empty() {
        return Err(declaration(format!(
            "{file_path} contains no {expected_kind}(...) declarations"
        )));
    }
    Ok(headers)
}

fn syntax_message(kind: &str, file_path: &str, error: &str) -> String {
    format!("{kind}(...) in '{file_path}' contains invalid SQLBuild header syntax: {error}")
}

/// `(ENUM|CONSTANT|SCHEMA)\s*\(` at `start`: the kind and the byte offset of the parenthesis.
fn declaration_start(contents: &str, start: usize) -> Option<(&'static str, usize)> {
    let rest: &str = &contents[start..];
    let kind: &'static str = DECLARATION_KINDS
        .into_iter()
        .find(|kind| rest.starts_with(kind))?;
    let open_index: usize = skip_whitespace(contents, start + kind.len());
    (contents.as_bytes().get(open_index) == Some(&b'(')).then_some((kind, open_index))
}

/// `_find_closing_parenthesis`: quotes skip backslash escapes; `None` when the header never closes.
fn closing_parenthesis(contents: &str, open_index: usize) -> Option<usize> {
    let bytes: &[u8] = contents.as_bytes();
    let mut depth: usize = 1;
    let mut quote: Option<u8> = None;
    let mut index: usize = open_index + 1;
    while index < bytes.len() {
        let byte: u8 = bytes[index];
        if let Some(open_quote) = quote {
            if byte == b'\\' {
                index += 1 + next_char_len(contents, index + 1);
                continue;
            }
            if byte == open_quote {
                quote = None;
            }
            index += 1;
            continue;
        }
        match byte {
            b'\'' | b'"' => quote = Some(byte),
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(index);
                }
            }
            _ => {}
        }
        index += 1;
    }
    None
}

/// The UTF-8 length of the character at `index`, or 0 at the end.
fn next_char_len(contents: &str, index: usize) -> usize {
    contents
        .get(index..)
        .and_then(|rest| rest.chars().next())
        .map_or(0, char::len_utf8)
}

/// The byte offset of the first non-whitespace character at or after `start`.
fn skip_whitespace(contents: &str, start: usize) -> usize {
    contents[start..]
        .char_indices()
        .find(|(_, character)| !is_python_space(*character))
        .map_or(contents.len(), |(offset, _)| start + offset)
}
