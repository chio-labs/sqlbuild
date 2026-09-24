//! Conservative native fast path for logical SQL reference extraction.

use crate::constants::{DBT_REFERENCE_KIND, TABLE_FUNCTION_REFERENCE_KIND};
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::main::quote_end::quote_end;
use crate::sql_scan::models::QuotePolicy;

const PREFIXES: [(&str, &str); 6] = [
    ("__dbt_ref(", "dbt_ref"),
    ("__table_fn(", "table_function"),
    ("__source(", "source"),
    ("__seed(", "seed"),
    ("__udf(", "udf"),
    ("__ref(", "ref"),
];

pub(crate) type StaticReference = (String, String, Option<String>, Option<usize>);

pub(crate) fn extract(sql: &str) -> Option<Vec<StaticReference>> {
    let bytes = sql.as_bytes();
    let mut references: Vec<StaticReference> = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        match non_code_end(bytes, index, QuotePolicy::COMPILER) {
            Ok(Some(end)) => {
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(_) => return None,
        }
        let Some((prefix, kind)) = PREFIXES
            .iter()
            .find(|(prefix, _)| bytes[index..].starts_with(prefix.as_bytes()))
        else {
            index += 1;
            continue;
        };
        if *kind == TABLE_FUNCTION_REFERENCE_KIND {
            return None;
        }
        let (first_name, first_end) = reference_name(sql, index + prefix.len())?;
        let mut cursor = ascii_whitespace_end(bytes, first_end);
        let mut package = None;
        let name;
        if *kind == DBT_REFERENCE_KIND && bytes.get(cursor).copied() == Some(b',') {
            cursor = ascii_whitespace_end(bytes, cursor + 1);
            let (second_name, second_end) = reference_name(sql, cursor)?;
            cursor = ascii_whitespace_end(bytes, second_end);
            package = Some(first_name);
            name = second_name;
        } else {
            name = first_name;
        }
        if bytes.get(cursor).copied() != Some(b')') {
            return None;
        }
        references.push(((*kind).to_owned(), name, package, None));
        index = cursor + 1;
    }
    Some(references)
}

fn reference_name(sql: &str, start: usize) -> Option<(String, usize)> {
    let bytes = sql.as_bytes();
    let start = ascii_whitespace_end(bytes, start);
    let first = bytes.get(start).copied()?;
    if matches!(first, b'\'' | b'"') {
        let Ok(end) = quote_end(bytes, start, QuotePolicy::COMPILER) else {
            return None;
        };
        return Some((sql[start + 1..end - 1].to_owned(), end));
    }
    if !is_identifier_start(first) {
        return None;
    }
    let mut end = start + 1;
    while bytes.get(end).copied().is_some_and(is_identifier_continue) {
        end += 1;
    }
    if bytes.get(end).is_some_and(|value| !value.is_ascii()) {
        return None;
    }
    Some((sql[start..end].to_owned(), end))
}

fn ascii_whitespace_end(bytes: &[u8], start: usize) -> usize {
    let mut end = start;
    while bytes
        .get(end)
        .is_some_and(|value| value.is_ascii_whitespace())
    {
        end += 1;
    }
    end
}

fn is_identifier_start(value: u8) -> bool {
    value.is_ascii_alphabetic()
}

fn is_identifier_continue(value: u8) -> bool {
    value.is_ascii_alphanumeric() || value == b'_'
}
