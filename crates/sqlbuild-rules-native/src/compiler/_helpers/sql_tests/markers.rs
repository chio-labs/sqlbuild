//! Marker and call-site text replacement shared by SQL-test planning.

use std::collections::HashSet;

use regex::Regex;

use crate::compiler::_helpers::sql_tests::planning::compile_error;

pub(crate) fn replace_callable_markers<F>(
    sql: &str,
    pattern: &Regex,
    protected_pattern: &Regex,
    mut replacement: F,
) -> Result<(String, HashSet<String>), String>
where
    F: FnMut(&str, &str) -> Option<(String, bool)>,
{
    let protected = protected_ranges(protected_pattern, sql);
    let mut output = String::with_capacity(sql.len());
    let mut reached: HashSet<String> = HashSet::new();
    let mut cursor = 0;
    for captures in pattern.captures_iter(sql) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        if full.start() < cursor || in_protected_range(full.start(), &protected) {
            continue;
        }
        let suffix_start = skip_whitespace(sql, full.end());
        if !sql[suffix_start..].starts_with('(') {
            continue;
        }
        let suffix_end = matching_paren_end(sql, suffix_start)?;
        let Some(name) = captures.get(1).map(|value| value.as_str()) else {
            continue;
        };
        let call_suffix = &sql[suffix_start..suffix_end];
        let Some((value, records_reach)) = replacement(name, call_suffix) else {
            continue;
        };
        output.push_str(&sql[cursor..full.start()]);
        output.push_str(&value);
        cursor = suffix_end;
        if records_reach {
            reached.insert(name.to_string());
        }
    }
    output.push_str(&sql[cursor..]);
    Ok((output, reached))
}

fn matching_paren_end(sql: &str, open: usize) -> Result<usize, String> {
    let bytes = sql.as_bytes();
    let mut depth = 0usize;
    let mut index = open;
    while index < bytes.len() {
        match bytes[index] {
            b'\'' | b'"' | b'`' => index = skip_quoted(sql, index)?,
            b'-' if bytes.get(index + 1) == Some(&b'-') => {
                index = sql[index..]
                    .find('\n')
                    .map_or(bytes.len(), |offset| index + offset + 1)
            }
            b'/' if bytes.get(index + 1) == Some(&b'*') => {
                let Some(offset) = sql[index + 2..].find("*/") else {
                    return Err(compile_error(
                        "SQL function call contains an unclosed block comment",
                    ));
                };
                index += offset + 4;
            }
            b'(' => {
                depth += 1;
                index += 1;
            }
            b')' => {
                depth -= 1;
                index += 1;
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => index += 1,
        }
    }
    Err(compile_error(
        "SQL function call contains an unclosed parenthesis",
    ))
}

fn skip_quoted(sql: &str, start: usize) -> Result<usize, String> {
    let quote = sql.as_bytes()[start];
    let bytes = sql.as_bytes();
    let mut index = start + 1;
    while index < bytes.len() {
        if bytes[index] != quote {
            index += 1;
            continue;
        }
        if bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Ok(index + 1);
    }
    Err(compile_error(
        "SQL function call contains an unclosed quoted string",
    ))
}

pub(crate) fn replace_named_markers<F>(
    sql: &str,
    pattern: &Regex,
    protected_pattern: &Regex,
    mut replacement: F,
) -> String
where
    F: FnMut(&str) -> Option<String>,
{
    let protected = protected_ranges(protected_pattern, sql);
    let mut output = String::with_capacity(sql.len());
    let mut cursor = 0;
    for captures in pattern.captures_iter(sql) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        if in_protected_range(full.start(), &protected) {
            continue;
        }
        let Some(name) = captures.get(1).map(|value| value.as_str()) else {
            continue;
        };
        let Some(value) = replacement(name) else {
            continue;
        };
        output.push_str(&sql[cursor..full.start()]);
        output.push_str(&value);
        cursor = full.end();
    }
    output.push_str(&sql[cursor..]);
    output
}

pub(crate) fn replace_dbt_ref_markers<F>(
    sql: &str,
    pattern: &Regex,
    protected_pattern: &Regex,
    mut replacement: F,
) -> String
where
    F: FnMut(&str) -> Option<String>,
{
    let protected = protected_ranges(protected_pattern, sql);
    let mut output = String::with_capacity(sql.len());
    let mut cursor = 0;
    for captures in pattern.captures_iter(sql) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        if in_protected_range(full.start(), &protected) {
            continue;
        }
        let Some(first) = captures.get(1).map(|value| value.as_str()) else {
            continue;
        };
        let name = captures.get(2).map_or_else(
            || first.to_string(),
            |second| format!("{first}__{}", second.as_str()),
        );
        let Some(value) = replacement(&name) else {
            continue;
        };
        output.push_str(&sql[cursor..full.start()]);
        output.push_str(&value);
        cursor = full.end();
    }
    output.push_str(&sql[cursor..]);
    output
}

pub(crate) fn marker_names(pattern: &Regex, protected_pattern: &Regex, sql: &str) -> Vec<String> {
    let protected = protected_ranges(protected_pattern, sql);
    let mut names: Vec<String> = Vec::new();
    for captures in pattern.captures_iter(sql) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        if in_protected_range(full.start(), &protected) {
            continue;
        }
        if let Some(name) = captures.get(1) {
            names.push(name.as_str().to_string());
        }
    }
    names
}

pub(crate) fn protected_ranges(pattern: &Regex, sql: &str) -> Vec<(usize, usize)> {
    pattern
        .find_iter(sql)
        .map(|value| (value.start(), value.end()))
        .collect()
}

pub(crate) fn in_protected_range(index: usize, ranges: &[(usize, usize)]) -> bool {
    ranges
        .iter()
        .any(|(start, end)| index >= *start && index < *end)
}

fn skip_whitespace(sql: &str, mut index: usize) -> usize {
    while sql
        .as_bytes()
        .get(index)
        .is_some_and(u8::is_ascii_whitespace)
    {
        index += 1;
    }
    index
}
