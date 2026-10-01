use std::str::FromStr;

use polyglot_sql::{Dialect, DialectType};
use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::main::formatter::format_json;
use crate::sql_tokens::main::canonical_tokens::canonical_tokens;
use crate::sql_tokens::main::query_fingerprint::query_fingerprint;

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
        let printed = actual.as_str().unwrap_or(sql);
        assert!(
            only_keyword_case_differs(sql, printed, dialect)?,
            "{dialect} fingerprint changed beyond keyword case: {sql}"
        );
        let previous_layout: Option<String> = entry["previously_formatted"]
            .as_str()
            .map(|previous| relaid_previous_layout(previous, dialect))
            .transpose()?;
        let layouts = [
            entry["formatted"].as_str().map(str::to_string),
            previous_layout,
        ];
        for stable in layouts.iter().flatten() {
            let stable = stable.as_str();
            let again = format_once(stable, dialect, None)?;
            assert_eq!(again["sql"], stable, "{dialect} layout drifted: {stable}");
            assert_eq!(
                again["changed"], false,
                "{dialect} layout drifted: {stable}"
            );
            assert_eq!(
                query_fingerprint(again["sql"].as_str().unwrap_or_default(), dialect)?,
                query_fingerprint(stable, dialect)?,
                "{dialect} formatting changed the fingerprint of formatted SQL: {stable}"
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

/// Whether `printed` has the fingerprint tokens of `sql` except for words upper-cased by format.
fn only_keyword_case_differs(sql: &str, printed: &str, dialect: &str) -> Result<bool, String> {
    let parser = Dialect::get(DialectType::from_str(dialect).map_err(|error| error.to_string())?);
    let left_tokens = parser.tokenize(sql).map_err(|error| error.to_string())?;
    let right_tokens = parser
        .tokenize(printed)
        .map_err(|error| error.to_string())?;
    let left = canonical_tokens(sql, &left_tokens, &parser)?;
    let right = canonical_tokens(printed, &right_tokens, &parser)?;
    Ok(left.len() == right.len()
        && left.iter().zip(&right).all(|(before, after)| {
            before == after
                || (before.text.eq_ignore_ascii_case(&after.text)
                    && after.text == after.text.to_ascii_uppercase())
        }))
}

/// Re-format a layout of an earlier formatter release, which must keep its fingerprint.
fn relaid_previous_layout(previous: &str, dialect: &str) -> Result<String, String> {
    let relaid = format_once(previous, dialect, None)?;
    let sql = relaid["sql"].as_str().unwrap_or_default().to_string();
    assert_eq!(
        query_fingerprint(&sql, dialect)?,
        query_fingerprint(previous, dialect)?,
        "{dialect} formatting changed the fingerprint of a previous layout: {previous}"
    );
    Ok(sql)
}

pub(crate) fn format_at_width(
    sql: &str,
    dialect: &str,
    line_width: usize,
) -> Result<Value, String> {
    format_once(sql, dialect, Some(line_width))
}

fn format_once(sql: &str, dialect: &str, line_width: Option<usize>) -> Result<Value, String> {
    let request = json!({"version": 1, "sql": sql, "dialect": dialect, "line_width": line_width});
    let response = format_json(&request.to_string())?;
    serde_json::from_str(&response).map_err(|error| error.to_string())
}
