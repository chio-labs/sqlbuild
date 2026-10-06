use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_quality::tests::test_types::QualityRuleTestCase;

pub(crate) fn lint(test_case: &QualityRuleTestCase) -> Result<Vec<Value>, String> {
    let relation_keys: Value =
        serde_json::from_str(test_case.relation_keys).map_err(|error| error.to_string())?;
    let request: Value = json!({
        "version": 1,
        "sql": test_case.sql,
        "dialect": "duckdb",
        "enabled_rules": [test_case.rule],
        "max_literal_length": 24,
        "max_ranking_order_by": 2,
        "relation_keys": relation_keys,
    });
    let response: Value = serde_json::from_str(&lint_json(&request.to_string())?)
        .map_err(|error| error.to_string())?;
    Ok(response["diagnostics"]
        .as_array()
        .cloned()
        .unwrap_or_default())
}

/// Lint `sql` in `dialect` with only `rule` enabled.
pub(crate) fn lint_dialect(sql: &str, dialect: &str, rule: &str) -> Result<Vec<Value>, String> {
    let request: Value = json!({
        "version": 1,
        "sql": sql,
        "dialect": dialect,
        "enabled_rules": [rule],
    });
    let response: Value = serde_json::from_str(&lint_json(&request.to_string())?)
        .map_err(|error| error.to_string())?;
    Ok(response["diagnostics"]
        .as_array()
        .cloned()
        .unwrap_or_default())
}

/// One DuckDB SELECT that parses each of `column_count` payload columns twice.
pub(crate) fn wide_json_select(column_count: usize) -> String {
    let projections: Vec<String> = (0..column_count * 2)
        .map(|index| format!("json(e.c{})->>'f{index}' AS f{index}", index % column_count))
        .collect();
    format!("SELECT {} FROM events AS e", projections.join(", "))
}

pub(crate) fn anchors(sql: &str, diagnostics: &[Value]) -> Vec<String> {
    diagnostics
        .iter()
        .map(|diagnostic| {
            let start: usize = diagnostic["start"].as_u64().unwrap_or(0) as usize;
            let end: usize = diagnostic["end"].as_u64().unwrap_or(0) as usize;
            sql.chars()
                .skip(start)
                .take(end.saturating_sub(start))
                .collect()
        })
        .collect()
}

pub(crate) fn fixed(sql: &str, diagnostics: &[Value]) -> Option<String> {
    let mut edits: Vec<(usize, usize, String)> = diagnostics
        .iter()
        .filter_map(|diagnostic| {
            let fix: &Value = diagnostic.get("fix")?;
            Some((
                fix["start"].as_u64()? as usize,
                fix["end"].as_u64()? as usize,
                fix["replacement"].as_str()?.to_owned(),
            ))
        })
        .collect();
    edits.sort_by_key(|edit| std::cmp::Reverse(edit.0));
    let applied: bool = !edits.is_empty();
    let mut characters: Vec<char> = sql.chars().collect();
    for (start, end, replacement) in edits {
        characters.splice(start..end, replacement.chars());
    }
    applied.then(|| characters.into_iter().collect())
}

/// A chain of CTEs that each drop their last column and rank without a declared key.
pub(crate) fn wide_cte_chain(cte_count: usize, column_count: usize) -> String {
    let columns: Vec<String> = (0..column_count).map(|index| format!("c{index}")).collect();
    let mut ctes: Vec<String> = vec![format!(
        "step_0 AS (SELECT {} FROM source_rows AS s)",
        columns
            .iter()
            .map(|column| format!("s.{column}"))
            .collect::<Vec<_>>()
            .join(", ")
    )];
    for step in 1..cte_count {
        let mut outputs: Vec<String> = columns[..column_count - 1]
            .iter()
            .map(|column| format!("p.{column}"))
            .collect();
        outputs.push(format!(
            "ROW_NUMBER() OVER (PARTITION BY p.c0 ORDER BY p.c1) AS c{}",
            column_count - 1
        ));
        ctes.push(format!(
            "step_{step} AS (SELECT {} FROM step_{} AS p)",
            outputs.join(", "),
            step - 1
        ));
    }
    format!(
        "WITH {} SELECT * FROM step_{}",
        ctes.join(",\n"),
        cte_count - 1
    )
}
