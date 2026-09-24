//! Marker and call-site text replacement shared by SQL-test planning.

use std::collections::HashSet;

use regex::{Captures, Regex};

use crate::compiler::_helpers::sql_tests::planning::compile_error;
use crate::compiler::_helpers::sql_tests::sql_scan::{Unclosed, matching_paren, skip_whitespace};

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
    matching_paren(sql, open)
        .map(|close| close + 1)
        .map_err(|error| {
            compile_error(match error {
                Unclosed::BlockComment => "SQL function call contains an unclosed block comment",
                Unclosed::Quote => "SQL function call contains an unclosed quoted string",
                Unclosed::Parenthesis => "SQL function call contains an unclosed parenthesis",
            })
        })
}

pub(crate) fn replace_named_markers<F>(
    sql: &str,
    pattern: &Regex,
    protected_pattern: &Regex,
    replacement: F,
) -> String
where
    F: FnMut(&str) -> Option<String>,
{
    replace_marker_captures(
        sql,
        pattern,
        protected_pattern,
        |captures| captures.get(1).map(|value| value.as_str().to_string()),
        replacement,
    )
}

pub(crate) fn replace_dbt_ref_markers<F>(
    sql: &str,
    pattern: &Regex,
    protected_pattern: &Regex,
    replacement: F,
) -> String
where
    F: FnMut(&str) -> Option<String>,
{
    replace_marker_captures(
        sql,
        pattern,
        protected_pattern,
        |captures| {
            let first = captures.get(1)?.as_str();
            Some(captures.get(2).map_or_else(
                || first.to_string(),
                |second| format!("{first}__{}", second.as_str()),
            ))
        },
        replacement,
    )
}

fn replace_marker_captures<N, F>(
    sql: &str,
    pattern: &Regex,
    protected_pattern: &Regex,
    marker_name: N,
    mut replacement: F,
) -> String
where
    N: Fn(&Captures<'_>) -> Option<String>,
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
        let Some(name) = marker_name(&captures) else {
            continue;
        };
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
