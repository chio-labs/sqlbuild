//! Python's `parse_sql_hook_file`: exactly one `HOOK(...);` header and the SQL after it.

use crate::_helpers::statement_headers::{StatementHeader, parse_statement_header};
use crate::declaration_files::_helpers::checks::python_values::{
    WordRules, failure, get, non_empty_str, python_str,
};
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::declaration_files::models::{DeclarationFileOptions, HookFile};
use crate::models::FailureKind;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::python_cleandoc::python_cleandoc;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

const HOOK_KEYWORD: &str = "HOOK";
const DESCRIPTION_KEY: &str = "description";
const SQL_QUOTES: &[u8] = b"'\"`";

fn hook_failure(message: String) -> ParseStop {
    failure(FailureKind::SqlHook, message)
}

pub(crate) fn parse_hook_file(
    file_path: &str,
    name: &str,
    contents: String,
    options: &DeclarationFileOptions,
) -> Result<HookFile, ParseStop> {
    let (header_start, header_end, body_start) = split_hook_file(&contents, file_path)?;
    let header: &str = &contents[header_start..header_end];
    let header_values: Vec<(String, AuthoredValue)> = parse_statement_header(
        &StatementHeader {
            kind: FailureKind::SqlHook,
            statement_name: HOOK_KEYWORD,
            statement: "HOOK()",
            file_path,
            supported_keys: &options.hook_keys,
            python: options.python,
        },
        header,
        contents[..header_start].matches('\n').count() + 1,
    )?;
    let description: Option<String> = match get(&header_values, DESCRIPTION_KEY) {
        Some(value) => {
            if non_empty_str(
                value,
                WordRules {
                    python: options.python,
                    file_path,
                },
            )?
            .is_none()
            {
                return Err(hook_failure(format!(
                    "HOOK() description in '{file_path}' must be a non-empty string"
                )));
            }
            python_str(
                value,
                WordRules {
                    python: options.python,
                    file_path,
                },
            )?
            .map(str::to_owned)
        }
        None => None,
    };
    let sql_body: String = python_cleandoc(options.python, &contents[body_start..]);
    if sql_body.is_empty() {
        return Err(hook_failure(format!(
            "SQL hook '{file_path}' must define SQL after HOOK(...)"
        )));
    }
    Ok(HookFile {
        header_values,
        sql_body,
        name: name.to_owned(),
        description,
        contents,
    })
}

/// `_split_hook_file`: byte offsets of the header start and end, and of the SQL after `;`.
fn split_hook_file(contents: &str, file_path: &str) -> Result<(usize, usize, usize), ParseStop> {
    let bytes: &[u8] = contents.as_bytes();
    let mut index: usize = skip_whitespace(contents, 0);
    if !contents[index..].starts_with(HOOK_KEYWORD) {
        return Err(hook_failure(format!(
            "SQL hook '{file_path}' must start with a HOOK() header as the first non-whitespace \
             content"
        )));
    }
    index = skip_whitespace(contents, index + HOOK_KEYWORD.len());
    if bytes.get(index) != Some(&b'(') {
        return Err(hook_failure(format!(
            "SQL hook '{file_path}' must define a HOOK(...) header"
        )));
    }
    let header_start: usize = index + 1;
    let mut depth: usize = 1;
    let mut quote: Option<u8> = None;
    index = header_start;
    while index < bytes.len() {
        let byte: u8 = bytes[index];
        if let Some(open_quote) = quote {
            if byte == b'\\' {
                index += 1 + next_char_len(contents, index + 1);
                continue;
            }
            if byte == open_quote {
                if bytes.get(index + 1) == Some(&open_quote) {
                    index += 2;
                    continue;
                }
                quote = None;
            }
            index += 1;
            continue;
        }
        if SQL_QUOTES.contains(&byte) {
            quote = Some(byte);
        } else if byte == b'(' {
            depth += 1;
        } else if byte == b')' {
            depth -= 1;
            if depth == 0 {
                break;
            }
        }
        index += 1;
    }
    if depth != 0 {
        return Err(hook_failure(format!(
            "SQL hook '{file_path}' has an unterminated HOOK(...) header"
        )));
    }
    let header_end: usize = index;
    index = skip_whitespace(contents, index + 1);
    if bytes.get(index) != Some(&b';') {
        return Err(hook_failure(format!(
            "SQL hook '{file_path}' HOOK(...) header must end with ';'"
        )));
    }
    Ok((header_start, header_end, index + 1))
}

fn next_char_len(contents: &str, index: usize) -> usize {
    contents
        .get(index..)
        .and_then(|rest| rest.chars().next())
        .map_or(0, char::len_utf8)
}

fn skip_whitespace(contents: &str, start: usize) -> usize {
    contents[start..]
        .char_indices()
        .find(|(_, character)| !is_python_space(*character))
        .map_or(contents.len(), |(offset, _)| start + offset)
}
