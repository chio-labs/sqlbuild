//! The general reference scan of Python `extract_sql_references`, reproduced exactly.

use sqlbuild_core::text::main::is_python_space::is_python_space;

use crate::sql_references::constants::{
    DBT_REFERENCE_KIND, NAME_QUOTE_BYTES, NON_CODE_START_BYTES, PLACEHOLDER_NAMES, QUOTE_BYTES,
    QUOTED_NAME_MINIMUM_BYTES, REFERENCE_CONTEXT, REFERENCE_PREFIXES, TABLE_FUNCTION_CALL_CONTEXT,
    TABLE_FUNCTION_REFERENCE_KIND,
};
use crate::sql_references::models::{InvalidReferenceCall, ReferenceScan, SqlReference};
use crate::sql_references::types::ReferencePrefix;
use crate::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use crate::sql_scan::models::{LexicalSyntax, Unclosed};

/// Why the scan stopped before reaching the end of the SQL.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Stop {
    /// Python raises `CompileInputError` with this message.
    Failed(String),
    /// A character or construct whose classification only Python reproduces.
    Deferred,
}

type Scan<T> = Result<T, Stop>;

/// Why the scan of one text stopped, with the byte offset Python's error points at.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Stopped {
    /// Python raises this message for the quote or comment, or the call, starting at the offset.
    Failed(String, usize),
    Deferred,
}

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

/// One parsed call: a reference, or a rejected call without its start.
enum Parsed {
    Reference(SqlReference),
    Invalid(InvalidReferenceCall),
}

/// Return every reference and rejected call in `sql` in authored order.
pub(crate) fn scan_references(
    sql: &[u8],
    syntax: &LexicalSyntax,
) -> Result<ReferenceScan, Stopped> {
    let mut scan: ReferenceScan = ReferenceScan::default();
    let mut offsets: CharOffsets = CharOffsets::default();
    let mut index = 0;
    while index < sql.len() {
        if let Some(end) = non_code_end(sql, index, syntax, REFERENCE_CONTEXT)
            .map_err(|stop| stopped_at(stop, index))?
        {
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
            .find(|(prefix, _)| sql[index..].starts_with(prefix))
        else {
            index += 1;
            continue;
        };
        let (parsed, next) =
            parse_reference(sql, index, call, syntax).map_err(|stop| stopped_at(stop, index))?;
        match parsed {
            Parsed::Reference(reference) => scan.references.push(reference),
            Parsed::Invalid(invalid_call) => scan.invalid_calls.push(InvalidReferenceCall {
                start: offsets
                    .advance(sql, index)
                    .map_err(|stop| stopped_at(stop, index))?,
                ..invalid_call
            }),
        }
        index = next;
    }
    Ok(scan)
}

/// Parse the reference call at `start` as Python `_parse_reference_at` does.
fn parse_reference(
    sql: &[u8],
    start: usize,
    call: &ReferencePrefix,
    syntax: &LexicalSyntax,
) -> Scan<(Parsed, usize)> {
    let (prefix, kind) = *call;
    let open = start + prefix.len() - 1;
    let close = matching_paren(sql, open, syntax, REFERENCE_CONTEXT)?;
    let arguments = &sql[open + 1..close];
    let call_text = &sql[start..=close];
    let names = if kind == DBT_REFERENCE_KIND {
        dbt_reference_names(arguments)?
    } else {
        bare_name(arguments)?.map(|name| (name, None))
    };
    let Some((name, package)) = names else {
        let invalid = invalid_arguments(kind, sql, (start, open, close), syntax)?;
        return Ok((Parsed::Invalid(invalid), close + 1));
    };
    let mut call_argument_count = None;
    if kind == TABLE_FUNCTION_REFERENCE_KIND {
        let suffix = python_whitespace_end(sql, close + 1)?;
        if sql.get(suffix) != Some(&b'(') {
            let corrected_call = format!("{}()", example_call(kind, &[name.as_str()]));
            let invalid = InvalidReferenceCall {
                kind,
                call: utf8(call_text)?,
                start: 0,
                message: format!(
                    "{} must be followed by an argument list",
                    function_name(kind)
                ),
                help: format!(
                    "pass the function arguments in a second set of parentheses, using () for \
                     no arguments: {corrected_call}"
                ),
                corrected_call,
            };
            return Ok((Parsed::Invalid(invalid), close + 1));
        }
        let suffix_close = matching_paren(sql, suffix, syntax, TABLE_FUNCTION_CALL_CONTEXT)?;
        call_argument_count = Some(split_arguments(sql, suffix + 1, suffix_close, syntax)?.len());
    }
    Ok((
        Parsed::Reference(SqlReference {
            kind,
            name,
            package,
            call_argument_count,
        }),
        close + 1,
    ))
}

/// Python `_invalid_reference_arguments`: the P012 message, help and corrected call.
fn invalid_arguments(
    kind: &'static str,
    sql: &[u8],
    (start, open, close): (usize, usize, usize),
    syntax: &LexicalSyntax,
) -> Scan<InvalidReferenceCall> {
    let allowed: &[usize] = if kind == DBT_REFERENCE_KIND {
        &[1, 2]
    } else {
        &[1]
    };
    let authored: Option<Vec<String>> = authored_names(sql, open + 1, close, syntax)?
        .filter(|names| allowed.contains(&names.len()));
    let names: Vec<String> = authored.unwrap_or_else(|| {
        PLACEHOLDER_NAMES
            .iter()
            .find(|(candidate, _)| *candidate == kind)
            .map_or_else(Vec::new, |(_, names)| {
                names.iter().map(|name| (*name).to_owned()).collect()
            })
    });
    let name_refs: Vec<&str> = names.iter().map(String::as_str).collect();
    let mut corrected_call = example_call(kind, &name_refs);
    if kind == TABLE_FUNCTION_REFERENCE_KIND {
        corrected_call.push_str("(...)");
    }
    let accepted = if kind == DBT_REFERENCE_KIND {
        "one double-quoted model name, or a double-quoted package name and model name separated \
         by a comma"
    } else {
        "exactly one double-quoted name"
    };
    let call = utf8(&sql[start..=close])?;
    let words: Vec<&str> = call
        .split(is_python_space)
        .filter(|word| !word.is_empty())
        .collect();
    let prefix = function_name(kind);
    Ok(InvalidReferenceCall {
        kind,
        message: format!("{} is not a valid {prefix}() call", words.join(" ")),
        help: format!(
            "{prefix}() takes {accepted}, with no comments or extra spaces inside the \
             parentheses: {corrected_call}"
        ),
        corrected_call,
        call,
        start: 0,
    })
}

/// Python `_authored_reference_names`: each argument as a plain or quoted name, else `None`.
fn authored_names(
    sql: &[u8],
    start: usize,
    end: usize,
    syntax: &LexicalSyntax,
) -> Scan<Option<Vec<String>>> {
    let split = match split_arguments(sql, start, end, syntax) {
        Ok(split) => split,
        Err(Stop::Failed(_)) => return Ok(None),
        Err(Stop::Deferred) => return Err(Stop::Deferred),
    };
    let mut names: Vec<String> = Vec::with_capacity(split.len());
    for argument in split {
        let name: &[u8] = match (argument.first(), argument.last()) {
            (Some(first), Some(last))
                if argument.len() >= QUOTED_NAME_MINIMUM_BYTES
                    && first == last
                    && NAME_QUOTE_BYTES.contains(first) =>
            {
                &argument[1..argument.len() - 1]
            }
            _ => &argument,
        };
        if !is_authored_name(name) {
            return Ok(None);
        }
        names.push(utf8(name)?);
    }
    Ok(Some(names))
}

/// Python `[A-Za-z_][A-Za-z0-9_.]*` matched against the whole name.
fn is_authored_name(name: &[u8]) -> bool {
    name.first()
        .is_some_and(|first| first.is_ascii_alphabetic() || *first == b'_')
        && name[1..]
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.'))
}

/// Python `SqlReferenceKind.function_name`.
fn function_name(kind: &str) -> String {
    format!("__{kind}")
}

/// Python `SqlReferenceKind.example_call(*names, quote='"')`.
fn example_call(kind: &str, names: &[&str]) -> String {
    let quoted: Vec<String> = names
        .iter()
        .map(|name| format!("\"{}\"", name.replace('"', "\"\"")))
        .collect();
    format!("{}({})", function_name(kind), quoted.join(", "))
}

/// Python `"([^"]+)"` matched against the whole argument text; `None` when it does not match.
fn bare_name(arguments: &[u8]) -> Scan<Option<String>> {
    match quoted_name_end(arguments, 0) {
        Some(end) if end == arguments.len() => utf8(&arguments[1..end - 1]).map(Some),
        _ => Ok(None),
    }
}

/// Python `"([^"]+)"(?:\s*,\s*"([^"]+)")?` over the whole text: name and package, or `None`.
fn dbt_reference_names(arguments: &[u8]) -> Scan<Option<(String, Option<String>)>> {
    let Some(first_end) = quoted_name_end(arguments, 0) else {
        return Ok(None);
    };
    if first_end == arguments.len() {
        return Ok(Some((utf8(&arguments[1..first_end - 1])?, None)));
    }
    let separator = python_whitespace_end(arguments, first_end)?;
    if arguments.get(separator) != Some(&b',') {
        return Ok(None);
    }
    let second_start = python_whitespace_end(arguments, separator + 1)?;
    match quoted_name_end(arguments, second_start) {
        Some(end) if end == arguments.len() => Ok(Some((
            utf8(&arguments[second_start + 1..end - 1])?,
            Some(utf8(&arguments[1..first_end - 1])?),
        ))),
        _ => Ok(None),
    }
}

/// The offset after a `"name"` with at least one character starting at `start`.
fn quoted_name_end(arguments: &[u8], start: usize) -> Option<usize> {
    if arguments.get(start) != Some(&b'"') {
        return None;
    }
    let close = start
        + 1
        + arguments[start + 1..]
            .iter()
            .position(|byte| *byte == b'"')?;
    (close > start + 1).then_some(close + 1)
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

/// Python `str.strip()`, which strips `str.isspace()` characters.
fn python_strip(value: &[u8]) -> Scan<&[u8]> {
    let text: &str = std::str::from_utf8(value).map_err(|_| Stop::Deferred)?;
    Ok(text.trim_matches(is_python_space).as_bytes())
}

/// Python `_skip_whitespace`, which skips `str.isspace()` characters.
fn python_whitespace_end(sql: &[u8], start: usize) -> Scan<usize> {
    let mut index = start;
    while index < sql.len() {
        let character: char = char_at(sql, index)?;
        if !is_python_space(character) {
            break;
        }
        index += character.len_utf8();
    }
    Ok(index)
}

/// The character starting at byte `index` of UTF-8 text.
fn char_at(text: &[u8], index: usize) -> Scan<char> {
    let width: usize = (text[index].leading_ones() as usize).max(1);
    let encoded: &[u8] = text.get(index..index + width).ok_or(Stop::Deferred)?;
    std::str::from_utf8(encoded)
        .map_err(|_| Stop::Deferred)?
        .chars()
        .next()
        .ok_or(Stop::Deferred)
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

/// Converts increasing byte offsets of UTF-8 text into Python code-point offsets.
#[derive(Default)]
struct CharOffsets {
    byte: usize,
    char: usize,
}

impl CharOffsets {
    fn advance(&mut self, text: &[u8], byte: usize) -> Scan<usize> {
        self.char += std::str::from_utf8(&text[self.byte..byte])
            .map_err(|_| Stop::Deferred)?
            .chars()
            .count();
        self.byte = byte;
        Ok(self.char)
    }
}

/// Point a stop at `start`: the top-level quote or comment, or the call being parsed.
fn stopped_at(stop: Stop, start: usize) -> Stopped {
    match stop {
        Stop::Failed(message) => Stopped::Failed(message, start),
        Stop::Deferred => Stopped::Deferred,
    }
}
