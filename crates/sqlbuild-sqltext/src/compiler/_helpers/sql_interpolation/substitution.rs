//! Conservative native fast path for compile-wide scalar SQL variables.

use std::collections::HashMap;

pub(crate) const UNCHANGED: u8 = 0;
pub(crate) const SUBSTITUTED: u8 = 1;
pub(crate) const FALLBACK: u8 = 2;

struct SubstitutionState {
    output: Option<String>,
    copy_start: usize,
}

pub(crate) fn substitute_batch(
    sqls: &[String],
    variables: &[(String, String)],
) -> Vec<(u8, Option<String>)> {
    let variables: HashMap<&str, &str> = variables
        .iter()
        .map(|(name, value)| (name.as_str(), value.as_str()))
        .collect();
    sqls.iter()
        .map(|sql| substitute_one(sql, &variables))
        .collect()
}

fn substitute_one(sql: &str, variables: &HashMap<&str, &str>) -> (u8, Option<String>) {
    if !sql.contains("@@") {
        return (UNCHANGED, None);
    }

    let bytes = sql.as_bytes();
    let mut state = SubstitutionState {
        output: None,
        copy_start: 0,
    };
    let mut index = 0;
    let mut quote: Option<u8> = None;
    while index < bytes.len() {
        if let Some(quote_byte) = quote {
            if bytes[index] == quote_byte {
                if matches!(quote_byte, b'\'' | b'"')
                    && bytes.get(index + 1).copied() == Some(quote_byte)
                {
                    index += 2;
                    continue;
                }
                quote = None;
                index += 1;
                continue;
            }
            if bytes[index..].starts_with(b"@@") {
                let Some((end, next_state)) = substitute_token(sql, index, variables, state) else {
                    return (FALLBACK, None);
                };
                state = next_state;
                index = end;
                continue;
            }
            index += 1;
            continue;
        }

        if bytes[index..].starts_with(b"--") {
            index = sql[index + 2..]
                .find('\n')
                .map_or(bytes.len(), |offset| index + 3 + offset);
            continue;
        }
        if bytes[index..].starts_with(b"/*") {
            let Some(offset) = sql[index + 2..].find("*/") else {
                return (FALLBACK, None);
            };
            index += offset + 4;
            continue;
        }
        if matches!(bytes[index], b'\'' | b'"' | b'`') {
            quote = Some(bytes[index]);
            index += 1;
            continue;
        }
        if bytes[index..].starts_with(b"@@") {
            let Some((end, next_state)) = substitute_token(sql, index, variables, state) else {
                return (FALLBACK, None);
            };
            state = next_state;
            index = end;
            continue;
        }
        index += 1;
    }
    if quote.is_some() {
        return (FALLBACK, None);
    }
    match state.output {
        Some(mut rendered) => {
            rendered.push_str(&sql[state.copy_start..]);
            (SUBSTITUTED, Some(rendered))
        }
        None => (UNCHANGED, None),
    }
}

fn substitute_token(
    sql: &str,
    start: usize,
    variables: &HashMap<&str, &str>,
    mut state: SubstitutionState,
) -> Option<(usize, SubstitutionState)> {
    let bytes = sql.as_bytes();
    if bytes[start..].starts_with(b"@@@") {
        let name_start = start + 3;
        let end = if bytes
            .get(name_start)
            .copied()
            .is_some_and(is_identifier_start)
        {
            consume_ascii_identifier(bytes, name_start)?
        } else {
            name_start
        };
        return Some((end, state));
    }
    let name_start = start + 2;
    if bytes[name_start..].starts_with(b"ENV:") || bytes[name_start..].starts_with(b"CTX:") {
        return None;
    }
    if !bytes
        .get(name_start)
        .copied()
        .is_some_and(is_identifier_start)
    {
        return None;
    }
    let name_end = consume_ascii_identifier(bytes, name_start)?;
    let name = &sql[name_start..name_end];
    let value = variables.get(name)?;
    let rendered = state
        .output
        .get_or_insert_with(|| String::with_capacity(sql.len()));
    rendered.push_str(&sql[state.copy_start..start]);
    rendered.push_str(value);
    state.copy_start = name_end;
    Some((name_end, state))
}

fn consume_ascii_identifier(bytes: &[u8], start: usize) -> Option<usize> {
    let mut end = start + 1;
    while bytes.get(end).copied().is_some_and(is_identifier_continue) {
        end += 1;
    }
    if bytes.get(end).is_some_and(|value| !value.is_ascii()) {
        return None;
    }
    Some(end)
}

fn is_identifier_start(value: u8) -> bool {
    value.is_ascii_alphabetic() || value == b'_'
}

fn is_identifier_continue(value: u8) -> bool {
    value.is_ascii_alphanumeric() || value == b'_'
}
