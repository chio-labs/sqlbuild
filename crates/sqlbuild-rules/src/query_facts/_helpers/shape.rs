use crate::query_facts::constants::{
    CALL_STUB, PLACEHOLDER_PREFIX, PLACEHOLDER_VALUE, REF_STUB, SOURCE_STUB, TABLE_FUNCTION_CALL,
    TABLE_FUNCTION_STUB, UDF_CALL, UDF_STUB,
};
use crate::query_facts::models::{CallKind, ModelCall, ModelShape};
use crate::rules::main::compact_sql::compact_sql;
use sqlbuild_analysis::semantic_validation::main::normalize_mapped::normalize_mapped;
use sqlbuild_sqltext::sql_scan::main::comment_end::comment_end;
use sqlbuild_sqltext::sql_scan::main::matching_paren::matching_paren;
use sqlbuild_sqltext::sql_scan::main::non_code_end::non_code_end;
use sqlbuild_sqltext::sql_scan::main::quote_policy::quote_policy;
use sqlbuild_sqltext::sql_scan::models::QuotePolicy;

pub(crate) fn model_shape(sql: &str, dialect: &str) -> Result<ModelShape, String> {
    let policy = QuotePolicy {
        dollar_quotes: true,
        ..quote_policy(dialect)
    };
    let nested = matches!(
        dialect.to_ascii_lowercase().as_str(),
        "generic" | "postgres" | "postgresql" | "mssql" | "sqlserver" | "tsql"
    );
    let (stubbed, stub_offsets, calls) = stub_calls(sql, policy, nested);
    let normalized = normalize_mapped(&stubbed, dialect)?;
    let end = stub_offsets.last().copied().unwrap_or_default();
    let offsets: Vec<usize> = normalized
        .offsets
        .iter()
        .map(|offset| stub_offsets.get(*offset).copied().unwrap_or(end))
        .collect();
    Ok(ModelShape {
        sql: normalized.sql,
        offsets,
        calls,
    })
}

/// Every `__ref`/`__source` call in code, as the dependency text rules compare.
pub(crate) fn dependency_texts(calls: &[ModelCall]) -> Vec<String> {
    calls
        .iter()
        .filter(|call| call.kind != CallKind::Other)
        .map(|call| call.text.clone())
        .collect()
}

pub(crate) fn stub_call(name: &str) -> Option<(CallKind, usize)> {
    for (prefix, kind) in [
        (REF_STUB, CallKind::Ref),
        (SOURCE_STUB, CallKind::Source),
        (CALL_STUB, CallKind::Other),
    ] {
        let Some(number) = name.strip_prefix(prefix) else {
            continue;
        };
        let Ok(number) = number.parse::<usize>() else {
            return None;
        };
        return Some((kind, number));
    }
    None
}

fn call_kind(word: &str) -> Option<CallKind> {
    match word {
        "__ref" => Some(CallKind::Ref),
        "__source" => Some(CallKind::Source),
        "__seed" | "__dbt_ref" => Some(CallKind::Other),
        _ => None,
    }
}

fn stub_prefix(kind: CallKind) -> &'static str {
    match kind {
        CallKind::Ref => REF_STUB,
        CallKind::Source => SOURCE_STUB,
        CallKind::Other => CALL_STUB,
    }
}

fn is_word_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'$'
}

fn nested_comment_end(bytes: &[u8], index: usize) -> Option<usize> {
    if !bytes[index..].starts_with(b"/*") {
        return None;
    }
    let mut depth = 0_usize;
    let mut cursor = index;
    while cursor < bytes.len() {
        if bytes[cursor..].starts_with(b"/*") {
            depth += 1;
            cursor += 2;
        } else if bytes[cursor..].starts_with(b"*/") {
            depth -= 1;
            cursor += 2;
            if depth == 0 {
                return Some(cursor);
            }
        } else {
            cursor += 1;
        }
    }
    Some(bytes.len())
}

fn skip_space(bytes: &[u8], mut index: usize) -> usize {
    loop {
        while bytes.get(index).is_some_and(u8::is_ascii_whitespace) {
            index += 1;
        }
        match comment_end(bytes, index) {
            Ok(Some(end)) => index = end,
            _ => return index,
        }
    }
}

fn quoted_name(sql: &str, open: usize) -> Option<(String, usize)> {
    let rest = sql.get(open..)?.strip_prefix("(\"")?;
    let length = rest.find('"')?;
    let name = &rest[..length];
    let valid = name
        .bytes()
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == b'_')
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_');
    let close = open + 2 + length + 1;
    (valid && sql.as_bytes().get(close) == Some(&b')')).then(|| (name.to_owned(), close))
}

fn stub_calls(
    sql: &str,
    policy: QuotePolicy,
    nested_comments: bool,
) -> (String, Vec<usize>, Vec<ModelCall>) {
    let bytes = sql.as_bytes();
    let mut edits: Vec<(usize, usize, String)> = Vec::new();
    let mut calls: Vec<ModelCall> = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        if nested_comments && let Some(end) = nested_comment_end(bytes, index) {
            index = end;
            continue;
        }
        match non_code_end(bytes, index, policy) {
            Ok(Some(end)) => {
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(_) => break,
        }
        if bytes[index..].starts_with(PLACEHOLDER_PREFIX)
            && bytes
                .get(index + PLACEHOLDER_PREFIX.len())
                .is_some_and(|byte| is_word_byte(*byte) && *byte != b'$')
        {
            let start = index;
            index += PLACEHOLDER_PREFIX.len();
            while index < bytes.len() && is_word_byte(bytes[index]) && bytes[index] != b'$' {
                index += 1;
            }
            edits.push((start, index, PLACEHOLDER_VALUE.to_owned()));
            continue;
        }
        if !(bytes[index].is_ascii_alphabetic() || bytes[index] == b'_') {
            index += 1;
            continue;
        }
        let start = index;
        while index < bytes.len() && is_word_byte(bytes[index]) {
            index += 1;
        }
        let word = sql[start..index].to_ascii_lowercase();
        if word == UDF_CALL || word == TABLE_FUNCTION_CALL {
            let Some((name, close)) = quoted_name(sql, index) else {
                continue;
            };
            let call = close + 1;
            let mut open = call;
            while bytes.get(open).is_some_and(u8::is_ascii_whitespace) {
                open += 1;
            }
            if bytes.get(open) != Some(&b'(') {
                continue;
            }
            let stub = if word == UDF_CALL {
                UDF_STUB
            } else {
                TABLE_FUNCTION_STUB
            };
            edits.push((start, open, format!("{stub}{name}")));
            index = open;
            continue;
        }
        let Some(kind) = call_kind(&word) else {
            continue;
        };
        let open = skip_space(bytes, index);
        if bytes.get(open) != Some(&b'(') {
            continue;
        }
        let Ok(close) = matching_paren(bytes, open, policy) else {
            continue;
        };
        let number = calls.len();
        calls.push(ModelCall {
            kind,
            text: format!("{word}{}", compact_sql(&sql[open..=close], policy)),
            target: call_target(&sql[open + 1..close]),
        });
        edits.push((start, close + 1, format!("{}{number}", stub_prefix(kind))));
        index = close + 1;
    }
    let mut stubbed = String::with_capacity(sql.len());
    let mut offsets: Vec<usize> = Vec::with_capacity(sql.len() + 1);
    let mut character = 0;
    let mut cursor = 0;
    for (start, end, replacement) in edits {
        for value in sql[cursor..start].chars() {
            stubbed.push(value);
            offsets.push(character);
            character += 1;
        }
        stubbed.push_str(&replacement);
        offsets.extend(std::iter::repeat_n(character, replacement.chars().count()));
        character += sql[start..end].chars().count();
        cursor = end;
    }
    for value in sql[cursor..].chars() {
        stubbed.push(value);
        offsets.push(character);
        character += 1;
    }
    offsets.push(character);
    (stubbed, offsets, calls)
}

fn call_target(arguments: &str) -> Option<String> {
    let argument = arguments.trim();
    for quote in ['"', '\''] {
        if let Some(inner) = argument
            .strip_prefix(quote)
            .and_then(|value| value.strip_suffix(quote))
        {
            let doubled = format!("{quote}{quote}");
            if inner.replace(&doubled, "").contains(quote) {
                return None;
            }
            return Some(inner.replace(&doubled, &quote.to_string()));
        }
    }
    (!argument.is_empty() && argument.bytes().all(is_word_byte)).then(|| argument.to_owned())
}
