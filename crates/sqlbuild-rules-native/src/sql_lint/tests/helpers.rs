use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::main::formatter::format_json;

pub(crate) fn nested_function_sql(depth: usize) -> String {
    format!("SELECT {}1{}", "F(".repeat(depth), ")".repeat(depth))
}

pub(crate) fn diagnostics(sql: &str) -> Result<Vec<Value>, String> {
    let response = lint_json(
        &json!({
            "version": 1,
            "sql": sql,
            "dialect": "snowflake"
        })
        .to_string(),
    )?;
    diagnostic_values(&response)
}

pub(crate) fn diagnostics_for_rules(sql: &str, rules: &[&str]) -> Result<Vec<Value>, String> {
    diagnostics_for_dialect(sql, "snowflake", rules)
}

pub(crate) fn diagnostics_for_dialect(
    sql: &str,
    dialect: &str,
    rules: &[&str],
) -> Result<Vec<Value>, String> {
    let request = json!({
        "version": 1,
        "sql": sql,
        "dialect": dialect,
        "enabled_rules": rules,
    });
    let response = lint_json(&request.to_string())?;
    diagnostic_values(&response)
}

fn diagnostic_values(response: &str) -> Result<Vec<Value>, String> {
    let payload: Value = serde_json::from_str(response).map_err(|error| error.to_string())?;
    payload["diagnostics"]
        .as_array()
        .cloned()
        .ok_or_else(|| "diagnostics should be an array".to_string())
}

/// A narrow width so that wrapping is exercised on most corpus queries.
const CORPUS_LINE_WIDTH: usize = 40;

/// Format every corpus query of one dialect and return the formatted and refused counts.
pub(crate) fn check_dialect_corpus(
    corpus: &[Value],
    dialect: &str,
) -> Result<(usize, usize), String> {
    let mut outcomes: Vec<bool> = Vec::new();
    for entry in corpus.iter().filter(|entry| entry["dialect"] == dialect) {
        let sql = entry["sql"].as_str().unwrap_or_default();
        let response = format_once(sql, dialect, None)?;
        let formatted = response["formatted"] == true;
        let actual = response
            .get("sql")
            .filter(|_| formatted)
            .cloned()
            .unwrap_or(Value::Null);
        let expected = entry["formatted"].as_str().map_or(Value::Null, Value::from);
        assert_eq!(actual, expected, "{dialect}: {sql}");
        let layouts = [&entry["formatted"], &entry["previously_formatted"]];
        for stable in layouts.iter().filter_map(|layout| layout.as_str()) {
            let again = format_once(stable, dialect, None)?;
            assert_eq!(again["sql"], stable, "{dialect} layout drifted: {stable}");
            assert_eq!(
                again["changed"], false,
                "{dialect} layout drifted: {stable}"
            );
        }
        let wrapped = format_once(sql, dialect, Some(CORPUS_LINE_WIDTH))?;
        assert_eq!(wrapped["formatted"], formatted, "{dialect} wrapped: {sql}");
        let wrapped_sql = wrapped["sql"].as_str().unwrap_or_default();
        let rewrapped = format_once(wrapped_sql, dialect, Some(CORPUS_LINE_WIDTH))?;
        assert_eq!(
            rewrapped["sql"], wrapped_sql,
            "{dialect} wrapping drifted: {sql}"
        );
        outcomes.push(formatted);
    }
    let formatted = outcomes.iter().filter(|outcome| **outcome).count();
    Ok((formatted, outcomes.len() - formatted))
}

fn format_once(sql: &str, dialect: &str, line_width: Option<usize>) -> Result<Value, String> {
    let request = json!({"version": 1, "sql": sql, "dialect": dialect, "line_width": line_width});
    let response = format_json(&request.to_string())?;
    serde_json::from_str(&response).map_err(|error| error.to_string())
}
