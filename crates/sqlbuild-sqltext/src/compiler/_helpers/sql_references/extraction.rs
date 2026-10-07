//! Conservative native fast path for logical SQL reference extraction.

use crate::compiler::types::StaticReference;
use crate::constants::{DBT_REFERENCE_KIND, TABLE_FUNCTION_REFERENCE_KIND};
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::QuotePolicy;

const PREFIXES: [(&str, &str); 6] = [
    ("__dbt_ref(", "dbt_ref"),
    ("__table_fn(", "table_function"),
    ("__source(", "source"),
    ("__seed(", "seed"),
    ("__udf(", "udf"),
    ("__ref(", "ref"),
];

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
        let mut cursor = first_end;
        let mut package = None;
        let name;
        let separator = ascii_whitespace_end(bytes, cursor);
        if *kind == DBT_REFERENCE_KIND && bytes.get(separator).copied() == Some(b',') {
            let second_start = ascii_whitespace_end(bytes, separator + 1);
            let (second_name, second_end) = reference_name(sql, second_start)?;
            cursor = second_end;
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

/// Read one bare `"name"` argument, the only form compile replacement accepts.
fn reference_name(sql: &str, start: usize) -> Option<(String, usize)> {
    let bytes = sql.as_bytes();
    if bytes.get(start).copied() != Some(b'"') {
        return None;
    }
    let close = start + 1 + bytes[start + 1..].iter().position(|value| *value == b'"')?;
    if close == start + 1 {
        return None;
    }
    Some((sql[start + 1..close].to_owned(), close + 1))
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
