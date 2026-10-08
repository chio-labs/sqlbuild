//! Reference calls in direct-logic helper and expected bodies, read as Python's reference scan.

use crate::constants::{DBT_REF_REFERENCE_KIND, TABLE_FUNCTION_TEST_MODE, UDF_TEST_MODE};
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_sqltext::sql_scan::main::dialect_matching_paren::dialect_matching_paren;
use sqlbuild_sqltext::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use sqlbuild_sqltext::sql_scan::models::{LexicalSyntax, Unclosed};

const PREFIXES: [(&str, &str); 6] = [
    ("__dbt_ref(", DBT_REF_REFERENCE_KIND),
    ("__table_fn(", TABLE_FUNCTION_TEST_MODE),
    ("__source(", "source"),
    ("__seed(", "seed"),
    ("__udf(", UDF_TEST_MODE),
    ("__ref(", "ref"),
];
const REFERENCE_CONTEXT: &str = "SQL reference";
const TABLE_FUNCTION_CALL_CONTEXT: &str = "SQL table function call";

/// The calls of one body that matter to direct-logic validation.
#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct BodyCalls {
    /// The kind of the first valid `__udf` or `__table_fn` call, in text order.
    pub(crate) first_logic_kind: Option<&'static str>,
    /// Whether any reference call is malformed, which Python reports as P012.
    pub(crate) invalid: bool,
}

/// Read every reference call outside comments and quoted text under the adapter's rules.
pub(crate) fn body_calls(sql: &str, syntax: &LexicalSyntax) -> Result<BodyCalls, String> {
    let bytes = sql.as_bytes();
    let mut calls = BodyCalls::default();
    let mut index = 0;
    while index < bytes.len() {
        if let Some(end) = dialect_non_code_end(bytes, index, syntax)
            .map_err(|error| unclosed(REFERENCE_CONTEXT, error))?
        {
            index = end;
            continue;
        }
        let Some((prefix, kind)) = PREFIXES
            .iter()
            .find(|(prefix, _)| bytes[index..].starts_with(prefix.as_bytes()))
        else {
            index += 1;
            continue;
        };
        let open = index + prefix.len() - 1;
        let close = paren(bytes, open, syntax, REFERENCE_CONTEXT)?;
        let arguments = &sql[open + 1..close];
        let mut valid = if *kind == DBT_REF_REFERENCE_KIND {
            dbt_arguments_match(arguments)
        } else {
            name_argument_matches(arguments)
        };
        if valid && *kind == TABLE_FUNCTION_TEST_MODE {
            let suffix = python_space_end(sql, close + 1);
            if bytes.get(suffix) == Some(&b'(') {
                let _ = paren(bytes, suffix, syntax, TABLE_FUNCTION_CALL_CONTEXT)?;
            } else {
                valid = false;
            }
        }
        if !valid {
            calls.invalid = true;
        } else if calls.first_logic_kind.is_none()
            && (*kind == UDF_TEST_MODE || *kind == TABLE_FUNCTION_TEST_MODE)
        {
            calls.first_logic_kind = Some(kind);
        }
        index = close + 1;
    }
    Ok(calls)
}

/// Python `"([^"]+)"` matched against the whole argument text.
fn name_argument_matches(arguments: &str) -> bool {
    quoted_name_end(arguments, 0) == Some(arguments.len())
}

/// Python `"([^"]+)"(?:\s*,\s*"([^"]+)")?` matched against the whole argument text.
fn dbt_arguments_match(arguments: &str) -> bool {
    let Some(first_end) = quoted_name_end(arguments, 0) else {
        return false;
    };
    if first_end == arguments.len() {
        return true;
    }
    let separator = python_space_end(arguments, first_end);
    if arguments.as_bytes().get(separator) != Some(&b',') {
        return false;
    }
    let second = python_space_end(arguments, separator + 1);
    quoted_name_end(arguments, second) == Some(arguments.len())
}

/// The offset after a `"name"` with at least one character starting at `start`.
fn quoted_name_end(arguments: &str, start: usize) -> Option<usize> {
    let bytes = arguments.as_bytes();
    if bytes.get(start) != Some(&b'"') {
        return None;
    }
    let close = start + 1 + bytes[start + 1..].iter().position(|byte| *byte == b'"')?;
    (close > start + 1).then_some(close + 1)
}

fn python_space_end(sql: &str, start: usize) -> usize {
    let mut index = start;
    while let Some(character) = sql.get(index..).and_then(|rest| rest.chars().next()) {
        if !is_python_space(character) {
            break;
        }
        index += character.len_utf8();
    }
    index
}

fn paren(sql: &[u8], open: usize, syntax: &LexicalSyntax, context: &str) -> Result<usize, String> {
    dialect_matching_paren(sql, open, syntax).map_err(|error| unclosed(context, error))
}

fn unclosed(context: &str, error: Unclosed) -> String {
    let construct = match error {
        Unclosed::BlockComment => "block comment",
        Unclosed::Quote => "quoted string",
        Unclosed::Parenthesis => "parenthesis",
    };
    format!("{context} contains an unclosed {construct}")
}
