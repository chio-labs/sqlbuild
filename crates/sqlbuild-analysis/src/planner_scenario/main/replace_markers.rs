//! Replace exact scenario relation markers without regenerating authored SQL.

use crate::planner_scenario::{_helpers::markers::marker_at, errors::MarkerError};
use sqlbuild_sqltext::code_scanner::main::{
    code_scanner::code_scanner, scanner_non_code_end::scanner_non_code_end,
};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

/// Resolve markers in execution order, optionally retaining the legacy unscanned dbt-ref policy.
pub fn replace_markers<E>(
    sql: &str,
    kind: usize,
    syntax: Option<LexicalSyntax>,
    mut resolve: impl FnMut(&str, &str) -> Result<String, E>,
) -> Result<String, MarkerError<E>> {
    let scanner = syntax.map(|syntax| code_scanner(sql, Some(syntax)));
    let offsets: Vec<usize> = sql
        .char_indices()
        .map(|(offset, _)| offset)
        .chain(std::iter::once(sql.len()))
        .collect();
    let mut index = 0;
    let mut last = 0;
    let mut result = String::new();
    while index + 1 < offsets.len() {
        if let Some(scanner) = &scanner
            && let Some(end) = scanner_non_code_end(scanner, index).map_err(MarkerError::Scan)?
        {
            index = end;
            continue;
        }
        let start = offsets[index];
        if let Some((end, name)) = marker_at(&sql[start..], kind) {
            let found = &sql[start..start + end];
            result.push_str(&sql[last..start]);
            result.push_str(&resolve(&name, found).map_err(MarkerError::Resolve)?);
            last = start + end;
            index += found.chars().count();
            continue;
        }
        index += 1;
    }
    result.push_str(&sql[last..]);
    Ok(result)
}
