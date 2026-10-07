//! The general reference scan of Python `extract_sql_references`, reproduced exactly.

use crate::sql_references::constants::{
    DBT_REFERENCE_KIND, NAME_QUOTE_BYTES, NON_CODE_START_BYTES, PAIRED_QUOTE_LENGTH,
    PYTHON_ASCII_WHITESPACE, QUOTE_BYTES, REFERENCE_CONTEXT, REFERENCE_PREFIXES,
    TABLE_FUNCTION_CALL_CONTEXT, TABLE_FUNCTION_REFERENCE_KIND,
};
use crate::sql_references::models::SqlReference;
use crate::sql_references::types::ReferencePrefix;
use crate::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use crate::sql_scan::models::{LexicalSyntax, Unclosed};

/// Why the scan stopped before reaching the end of the SQL.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Stop {
    /// Python raises `CompileInputError` with this message.
    Failed(String),
    /// A non-ASCII character decides the outcome, which needs Python's `str` classification.
    Deferred,
}

type Scan<T> = Result<T, Stop>;

const NON_CODE_START: [bool; 256] = byte_table(NON_CODE_START_BYTES, false);
const REFERENCE_SCAN_START: [bool; 256] = byte_table(NON_CODE_START_BYTES, true);

/// Mark `bytes`, and the underscore that starts every reference call when `underscore` is set.
const fn byte_table(bytes: &[u8], underscore: bool) -> [bool; 256] {
    let mut table = [false; 256];
    let mut index = 0;
    while index < bytes.len() {
        table[bytes[index] as usize] = true;
        index += 1;
    }
    table[b'_' as usize] = underscore;
    table
}

/// Return every reference in `sql` in authored order.
pub(crate) fn scan_references(sql: &[u8], syntax: &LexicalSyntax) -> Scan<Vec<SqlReference>> {
    let mut references: Vec<SqlReference> = Vec::new();
    let mut index = 0;
    while index < sql.len() {
        if let Some(end) = non_code_end(sql, index, syntax, REFERENCE_CONTEXT)? {
            index = end;
            continue;
        }
        if sql[index] != b'_' {
            index += 1;
            while index < sql.len() && !REFERENCE_SCAN_START[usize::from(sql[index])] {
                index += 1;
            }
            continue;
        }
        let Some(call) = REFERENCE_PREFIXES
            .iter()
            .find(|(prefix, _, _)| sql[index..].starts_with(prefix))
        else {
            index += 1;
            continue;
        };
        let (reference, next) = parse_reference(sql, index, call, syntax)?;
        references.push(reference);
        index = next;
    }
    Ok(references)
}

/// Parse the reference call starting at `start`, returning it and the offset after its name list.
fn parse_reference(
    sql: &[u8],
    start: usize,
    call: &ReferencePrefix,
    syntax: &LexicalSyntax,
) -> Scan<(SqlReference, usize)> {
    let (prefix, kind, call_name) = *call;
    let open = start + prefix.len() - 1;
    let close = matching_paren(sql, open, syntax, REFERENCE_CONTEXT)?;
    let arguments = split_arguments(sql, open + 1, close, syntax)?;
    if kind == DBT_REFERENCE_KIND {
        if !matches!(arguments.len(), 1 | 2) {
            return Err(failed(format!(
                "{call_name} must contain one name argument or package/name arguments"
            )));
        }
        if let [package, name] = arguments.as_slice() {
            let package = reference_name(package, kind, call_name)?;
            let name = reference_name(name, kind, call_name)?;
            return Ok((
                SqlReference {
                    kind,
                    name,
                    package: Some(package),
                    call_argument_count: None,
                },
                close + 1,
            ));
        }
    } else if arguments.len() != 1 {
        return Err(failed(format!(
            "{call_name} must contain exactly one name argument"
        )));
    }
    let mut call_argument_count = None;
    if kind == TABLE_FUNCTION_REFERENCE_KIND {
        let suffix = python_whitespace_end(sql, close + 1)?;
        if sql.get(suffix) != Some(&b'(') {
            return Err(failed(format!(
                "{call_name} must be followed by an argument list"
            )));
        }
        let suffix_close = matching_paren(sql, suffix, syntax, TABLE_FUNCTION_CALL_CONTEXT)?;
        call_argument_count = Some(split_arguments(sql, suffix + 1, suffix_close, syntax)?.len());
    }
    Ok((
        SqlReference {
            kind,
            name: reference_name(&arguments[0], kind, call_name)?,
            package: None,
            call_argument_count,
        },
        close + 1,
    ))
}

/// Python `_split_top_level_arguments` over `sql[start..end]`: comments read as one space.
fn split_arguments(
    sql: &[u8],
    start: usize,
    end: usize,
    syntax: &LexicalSyntax,
) -> Scan<Vec<Vec<u8>>> {
    let mut arguments: Vec<Vec<u8>> = Vec::new();
    let mut current: Vec<u8> = Vec::new();
    let mut depth = 0isize;
    let mut saw_separator = false;
    let mut index = start;
    while index < end {
        if let Some(non_code) = non_code_end(sql, index, syntax, REFERENCE_CONTEXT)? {
            if non_code > end {
                return Err(Stop::Deferred);
            }
            if QUOTE_BYTES.contains(&sql[index]) {
                current.extend_from_slice(&sql[index..non_code]);
            } else {
                current.push(b' ');
            }
            index = non_code;
            continue;
        }
        match sql[index] {
            b'(' => depth += 1,
            b')' => depth -= 1,
            b',' if depth == 0 => {
                let argument = python_strip(&current)?;
                if argument.is_empty() {
                    return Err(failed(format!(
                        "{REFERENCE_CONTEXT} contains an empty argument"
                    )));
                }
                arguments.push(argument.to_vec());
                current.clear();
                saw_separator = true;
                index += 1;
                continue;
            }
            _ => {}
        }
        current.push(sql[index]);
        index += 1;
    }
    let argument = python_strip(&current)?;
    if !argument.is_empty() {
        arguments.push(argument.to_vec());
    } else if saw_separator {
        return Err(failed(format!(
            "{REFERENCE_CONTEXT} contains an empty argument"
        )));
    }
    Ok(arguments)
}

/// Python `_parse_reference_name` for one stripped argument.
fn reference_name(argument: &[u8], kind: &str, call_name: &str) -> Scan<String> {
    let paired_quote = |quotes: &[u8]| {
        argument.len() >= PAIRED_QUOTE_LENGTH
            && argument[0] == argument[argument.len() - 1]
            && quotes.contains(&argument[0])
    };
    if kind == TABLE_FUNCTION_REFERENCE_KIND && !paired_quote(b"\"") {
        return Err(failed(format!(
            "{call_name} name argument must be double quoted"
        )));
    }
    if paired_quote(NAME_QUOTE_BYTES) {
        return utf8(&argument[1..argument.len() - 1]);
    }
    if identifier_validity(argument)? {
        return utf8(argument);
    }
    Err(failed(format!(
        "{call_name} name argument must be a quoted string or identifier"
    )))
}

/// Python `value.replace("_", "a").isalnum() and value[0].isalpha()` for a non-empty value.
fn identifier_validity(value: &[u8]) -> Scan<bool> {
    if value
        .iter()
        .any(|byte| byte.is_ascii() && !(byte.is_ascii_alphanumeric() || *byte == b'_'))
    {
        return Ok(false);
    }
    if value[0].is_ascii() && !value[0].is_ascii_alphabetic() {
        return Ok(false);
    }
    if value.is_ascii() {
        Ok(true)
    } else {
        Err(Stop::Deferred)
    }
}

/// Python `str.strip()`; a non-ASCII character at either edge may be Unicode whitespace.
fn python_strip(value: &[u8]) -> Scan<&[u8]> {
    let start = value
        .iter()
        .position(|byte| !PYTHON_ASCII_WHITESPACE.contains(byte))
        .unwrap_or(value.len());
    let end = value
        .iter()
        .rposition(|byte| !PYTHON_ASCII_WHITESPACE.contains(byte))
        .map_or(start, |last| last + 1);
    let stripped = &value[start..end];
    if stripped.first().is_some_and(|byte| !byte.is_ascii())
        || stripped.last().is_some_and(|byte| !byte.is_ascii())
    {
        return Err(Stop::Deferred);
    }
    Ok(stripped)
}

/// Python `_skip_whitespace`, which skips `str.isspace()` characters.
fn python_whitespace_end(sql: &[u8], start: usize) -> Scan<usize> {
    let mut index = start;
    while let Some(byte) = sql.get(index) {
        if !byte.is_ascii() {
            return Err(Stop::Deferred);
        }
        if !PYTHON_ASCII_WHITESPACE.contains(byte) {
            break;
        }
        index += 1;
    }
    Ok(index)
}

fn non_code_end(
    sql: &[u8],
    index: usize,
    syntax: &LexicalSyntax,
    context: &str,
) -> Scan<Option<usize>> {
    if !NON_CODE_START[usize::from(sql[index])] {
        return Ok(None);
    }
    dialect_non_code_end(sql, index, syntax).map_err(|unclosed| unclosed_error(context, unclosed))
}

/// Python `find_matching_paren`, which only looks for comments and quotes at special characters.
fn matching_paren(sql: &[u8], open: usize, syntax: &LexicalSyntax, context: &str) -> Scan<usize> {
    let mut depth = 1usize;
    let mut index = open + 1;
    while index < sql.len() {
        match sql[index] {
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => {
                if let Some(end) = non_code_end(sql, index, syntax, context)? {
                    index = end;
                    continue;
                }
            }
        }
        index += 1;
    }
    Err(unclosed_error(context, Unclosed::Parenthesis))
}

fn unclosed_error(context: &str, unclosed: Unclosed) -> Stop {
    let construct = match unclosed {
        Unclosed::BlockComment => "block comment",
        Unclosed::Quote => "quoted string",
        Unclosed::Parenthesis => "parenthesis",
    };
    failed(format!("{context} contains an unclosed {construct}"))
}

fn utf8(value: &[u8]) -> Scan<String> {
    String::from_utf8(value.to_vec()).map_err(|_| Stop::Deferred)
}

fn failed(message: String) -> Stop {
    Stop::Failed(message)
}
