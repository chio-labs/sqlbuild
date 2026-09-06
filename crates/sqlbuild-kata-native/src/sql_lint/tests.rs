use serde_json::{Value, json};

use super::engine::lint_json;
use super::formatter::format_json;

fn diagnostic_codes(sql: &str) -> Vec<String> {
    diagnostics(sql)
        .iter()
        .map(|diagnostic| {
            diagnostic["code"]
                .as_str()
                .expect("code should be a string")
                .to_string()
        })
        .collect()
}

fn diagnostics(sql: &str) -> Vec<Value> {
    let response = lint_json(
        &json!({
            "version": 1,
            "sql": sql,
            "dialect": "snowflake"
        })
        .to_string(),
    )
    .expect("lint should succeed");
    let payload: Value = serde_json::from_str(&response).expect("response should be JSON");
    payload["diagnostics"]
        .as_array()
        .expect("diagnostics should be an array")
        .clone()
}

#[test]
fn given_nested_queries_when_linting_then_diagnostics_anchor_to_risky_clauses() {
    let sql = "SELECT * FROM (SELECT id FROM inner_items ORDER BY id LIMIT 1) safe JOIN outer_items ON TRUE OFFSET 2";
    let found = diagnostics(sql);

    let spans: Vec<(&str, &str)> = found
        .iter()
        .map(|diagnostic| {
            let code = diagnostic["code"].as_str().expect("code should be text");
            let start = diagnostic["start"]
                .as_u64()
                .expect("start should be numeric") as usize;
            let end = diagnostic["end"].as_u64().expect("end should be numeric") as usize;
            (code, &sql[start..end])
        })
        .collect();

    assert!(spans.contains(&("SQBL003", "JOIN")), "{spans:?}");
    assert!(spans.contains(&("SQBL004", "OFFSET")));
    assert!(!spans.contains(&("SQBL004", "LIMIT")));
}

#[test]
fn given_unused_cte_chain_when_linting_then_all_unreachable_ctes_are_reported() {
    for (sql, expected_count) in [
        (
            "WITH first AS (SELECT 1), second AS (SELECT * FROM first) SELECT 1",
            2,
        ),
        (
            "WITH unused AS (SELECT 1 AS id) SELECT id FROM left_table UNION ALL SELECT id FROM right_table",
            1,
        ),
    ] {
        let codes = diagnostic_codes(sql);
        assert_eq!(
            codes
                .iter()
                .filter(|code| code.as_str() == "SQBL005")
                .count(),
            expected_count,
            "{sql}"
        );
    }
}

#[test]
fn given_positional_set_with_stars_when_linting_then_operation_is_reported_once() {
    for sql in [
        "SELECT * FROM a UNION ALL SELECT * FROM b",
        "(SELECT * FROM a) UNION ALL (SELECT id FROM b)",
    ] {
        let found: Vec<Value> = diagnostics(sql)
            .into_iter()
            .filter(|diagnostic| diagnostic["code"] == "SQBL007")
            .collect();

        assert_eq!(found.len(), 1, "{sql}");
        let start = found[0]["start"].as_u64().expect("start should be numeric") as usize;
        let end = found[0]["end"].as_u64().expect("end should be numeric") as usize;
        assert_eq!(&sql[start..end], "UNION");
    }
}

#[test]
fn given_multiple_statements_when_linting_then_all_statements_are_checked() {
    let sql = "SELECT value FROM first LIMIT 1; SELECT value FROM second OFFSET 1";
    let found: Vec<Value> = diagnostics(sql)
        .into_iter()
        .filter(|diagnostic| diagnostic["code"] == "SQBL004")
        .collect();

    assert_eq!(found.len(), 2);
    let anchored: Vec<&str> = found
        .iter()
        .map(|diagnostic| {
            let start = diagnostic["start"]
                .as_u64()
                .expect("start should be numeric") as usize;
            let end = diagnostic["end"].as_u64().expect("end should be numeric") as usize;
            &sql[start..end]
        })
        .collect();
    assert_eq!(anchored, ["LIMIT", "OFFSET"]);
}

#[test]
fn given_generic_sql_risks_when_linting_then_reports_native_rule_codes() {
    let cases = [
        ("SELECT * FROM a WHERE value = NULL", "SQBL001"),
        ("SELECT * FROM a WHERE (NULL) = value", "SQBL001"),
        ("SELECT a.id FROM a, b", "SQBL002"),
        ("SELECT a.id FROM a JOIN b", "SQBL003"),
        ("SELECT id FROM items LIMIT 1", "SQBL004"),
        ("WITH unused AS (SELECT 1) SELECT 1", "SQBL005"),
        ("SELECT DISTINCT id FROM items GROUP BY id", "SQBL006"),
        ("SELECT * FROM a UNION ALL SELECT * FROM b", "SQBL007"),
    ];

    for (sql, expected_code) in cases {
        assert!(
            diagnostic_codes(sql)
                .iter()
                .any(|code| code == expected_code),
            "expected {expected_code} for {sql}"
        );
    }
}

#[test]
fn given_safe_equivalents_when_linting_then_reports_no_native_diagnostics() {
    let cases = [
        "SELECT value FROM a WHERE value IS NULL",
        "SELECT value FROM a WHERE COALESCE(value, NULL) = 1",
        "UPDATE items SET value = NULL",
        "SELECT a.id FROM a CROSS JOIN b",
        "SELECT a.id FROM a JOIN b ON a.id = b.id",
        "SELECT id FROM items ORDER BY id LIMIT 1",
        "WITH used AS (SELECT 1 AS id) SELECT id FROM used",
        "SELECT id FROM items GROUP BY id",
        "SELECT DISTINCT a FROM items GROUP BY a, b",
        "SELECT DISTINCT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) FROM items",
        "SELECT id FROM a UNION ALL SELECT id FROM b",
        "SELECT id, name FROM (SELECT * FROM base) b UNION ALL SELECT id, name FROM other",
        "(SELECT id FROM (SELECT * FROM base) b) UNION ALL (SELECT id FROM other)",
    ];

    for sql in cases {
        assert_eq!(diagnostic_codes(sql), Vec::<String>::new(), "SQL: {sql}");
    }
}

#[test]
fn given_unknown_rule_when_linting_then_request_is_rejected() {
    let error = lint_json(
        &json!({
            "version": 1,
            "sql": "SELECT 1",
            "dialect": "snowflake",
            "enabled_rules": ["SQBL999"]
        })
        .to_string(),
    )
    .expect_err("unknown rules should fail closed");

    assert!(error.contains("unknown native lint rule 'SQBL999'"));
}

#[test]
fn given_comment_free_sql_when_formatting_then_returns_canonical_idempotent_sql() {
    let response = format_json(
        &json!({
            "version": 1,
            "sql": "select a,b from items where a=1",
            "dialect": "snowflake"
        })
        .to_string(),
    )
    .expect("format should succeed");
    let payload: Value = serde_json::from_str(&response).expect("response should be JSON");

    assert_eq!(payload["formatted"], true);
    assert_eq!(payload["changed"], true);
    assert_eq!(
        payload["sql"],
        "SELECT\n  a,\n  b\nFROM items\nWHERE\n  a = 1"
    );
}

#[test]
fn given_sql_comment_when_formatting_then_preserves_comment_attachment() {
    let sql = "SELECT a, /* preserve */ b FROM items";
    let response = format_json(
        &json!({
            "version": 1,
            "sql": sql,
            "dialect": "snowflake"
        })
        .to_string(),
    )
    .expect("commented SQL should format losslessly");
    let payload: Value = serde_json::from_str(&response).expect("response should be JSON");

    assert_eq!(payload["formatted"], true);
    assert_eq!(payload["changed"], true);
    assert_eq!(
        payload["sql"],
        "SELECT\n  a, /* preserve */\n  b\nFROM items"
    );
}

#[test]
fn given_line_and_leading_comments_when_formatting_then_comment_text_and_order_are_preserved() {
    let sql = "-- lead\nselect a,b from items -- tail\nwhere a=1";
    let response = format_json(
        &json!({
            "version": 1,
            "sql": sql,
            "dialect": "snowflake"
        })
        .to_string(),
    )
    .expect("commented SQL should format losslessly");
    let payload: Value = serde_json::from_str(&response).expect("response should be JSON");

    assert_eq!(
        payload["sql"],
        "-- lead\nSELECT\n  a,\n  b\nFROM items -- tail\nWHERE\n  a = 1"
    );
}

#[test]
fn given_comment_markers_inside_string_when_formatting_then_literal_is_not_treated_as_comment() {
    let response = format_json(
        &json!({
            "version": 1,
            "sql": "select '-- not a comment' as value",
            "dialect": "snowflake"
        })
        .to_string(),
    )
    .expect("string literal should format normally");
    let payload: Value = serde_json::from_str(&response).expect("response should be JSON");

    assert_eq!(payload["sql"], "SELECT\n  '-- not a comment' AS value");
}

#[test]
fn given_comment_after_statement_terminator_when_formatting_then_comment_is_preserved() {
    let response = format_json(
        &json!({
            "version": 1,
            "sql": "select a from items; -- retained",
            "dialect": "snowflake"
        })
        .to_string(),
    )
    .expect("trailing comment should format losslessly");
    let payload: Value = serde_json::from_str(&response).expect("response should be JSON");

    assert_eq!(payload["sql"], "SELECT\n  a\nFROM items -- retained\n");
}
