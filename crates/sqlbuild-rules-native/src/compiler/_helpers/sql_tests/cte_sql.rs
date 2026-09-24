//! CTE definition and leading-WITH assembly shared by SQL-test planning and rendering.

use crate::compiler::_helpers::sql_tests::sql_scan::{comment_end, skip_whitespace};

/// Render one `name AS (body)` definition, closing a trailing line comment first.
pub(crate) fn cte_definition_sql(name: &str, sql: &str) -> String {
    let body = sql.trim_end();
    let final_line = body.rsplit_once('\n').map_or(body, |(_, line)| line);
    let terminator = if final_line.contains("--") { "\n" } else { "" };
    format!("{name} AS ({body}{terminator})")
}

/// Append CTEs whose names are not already present, keeping first definitions and order.
pub(crate) fn with_unique_ctes(
    mut ctes: Vec<(String, String)>,
    extra: impl IntoIterator<Item = (String, String)>,
) -> Vec<(String, String)> {
    for (name, sql) in extra {
        if !ctes.iter().any(|(existing, _)| *existing == name) {
            ctes.push((name, sql));
        }
    }
    ctes
}

/// Prefix CTEs to a query, merging into its own leading WITH clause when present.
pub(crate) fn with_leading_ctes(ctes: &[(String, String)], body: &str) -> String {
    if ctes.is_empty() {
        return body.to_string();
    }
    let definitions: String = ctes
        .iter()
        .map(|(name, sql)| cte_definition_sql(name, sql))
        .collect::<Vec<_>>()
        .join(", ");
    match leading_with_prefix_end(body) {
        Some(end) => format!("{}{definitions}, {}", &body[..end], &body[end..]),
        None => format!("WITH {definitions} {body}"),
    }
}

/// Return the offset just after a leading `WITH` (and optional `RECURSIVE`) keyword.
pub(crate) fn leading_with_prefix_end(sql: &str) -> Option<usize> {
    let mut index = skip_leading_ignorable(sql, 0);
    index = keyword_end(sql, index, "WITH")?;
    index = skip_leading_ignorable(sql, index);
    if let Some(recursive_end) = keyword_end(sql, index, "RECURSIVE") {
        index = skip_leading_ignorable(sql, recursive_end);
    }
    Some(index)
}

fn skip_leading_ignorable(sql: &str, mut index: usize) -> usize {
    loop {
        index = skip_whitespace(sql, index);
        match comment_end(sql, index) {
            Ok(Some(end)) => index = end,
            Ok(None) | Err(_) => return index,
        }
    }
}

fn keyword_end(sql: &str, start: usize, keyword: &str) -> Option<usize> {
    let end = start + keyword.len();
    if !sql.get(start..end)?.eq_ignore_ascii_case(keyword) {
        return None;
    }
    if sql
        .as_bytes()
        .get(end)
        .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
    {
        return None;
    }
    Some(end)
}
