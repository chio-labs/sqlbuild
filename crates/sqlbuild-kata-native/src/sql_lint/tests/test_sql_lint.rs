use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::{helpers, test_types};

#[test]
fn given_sql_cases_when_linting_then_diagnostics_match() -> Result<(), String> {
    let test_cases = [
        test_types::LintTestCase {
            description: "NULL comparison",
            sql: "SELECT value FROM a WHERE value = NULL",
            expected_codes: &["SQBL001"],
            expected_anchors: &[("SQBL001", "=")],
        },
        test_types::LintTestCase {
            description: "wrapped NULL comparison",
            sql: "SELECT value FROM a WHERE (NULL) = value",
            expected_codes: &["SQBL001"],
            expected_anchors: &[("SQBL001", "=")],
        },
        test_types::LintTestCase {
            description: "implicit cartesian join",
            sql: "SELECT a.id FROM a, b",
            expected_codes: &["SQBL002"],
            expected_anchors: &[("SQBL002", ",")],
        },
        test_types::LintTestCase {
            description: "unconditioned join",
            sql: "SELECT a.id FROM a JOIN b",
            expected_codes: &["SQBL003"],
            expected_anchors: &[("SQBL003", "JOIN")],
        },
        test_types::LintTestCase {
            description: "unordered limit",
            sql: "SELECT id FROM items LIMIT 1",
            expected_codes: &["SQBL004"],
            expected_anchors: &[("SQBL004", "LIMIT")],
        },
        test_types::LintTestCase {
            description: "unused CTE",
            sql: "WITH unused AS (SELECT 1) SELECT 1",
            expected_codes: &["SQBL005"],
            expected_anchors: &[("SQBL005", "unused")],
        },
        test_types::LintTestCase {
            description: "unreachable CTE chain",
            sql: "WITH first AS (SELECT 1), second AS (SELECT * FROM first) SELECT 1",
            expected_codes: &["SQBL005", "SQBL005"],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "unused CTE on set operation",
            sql: "WITH unused AS (SELECT 1 AS id) SELECT id FROM left_table UNION ALL SELECT id FROM right_table",
            expected_codes: &["SQBL005"],
            expected_anchors: &[("SQBL005", "unused")],
        },
        test_types::LintTestCase {
            description: "redundant distinct",
            sql: "SELECT DISTINCT id FROM items GROUP BY id",
            expected_codes: &["SQBL006"],
            expected_anchors: &[("SQBL006", "DISTINCT")],
        },
        test_types::LintTestCase {
            description: "positional set star",
            sql: "SELECT * FROM a UNION ALL SELECT * FROM b",
            expected_codes: &["SQBL007"],
            expected_anchors: &[("SQBL007", "UNION")],
        },
        test_types::LintTestCase {
            description: "parenthesized positional set star",
            sql: "(SELECT * FROM a) UNION ALL (SELECT id FROM b)",
            expected_codes: &["SQBL007"],
            expected_anchors: &[("SQBL007", "UNION")],
        },
        test_types::LintTestCase {
            description: "multiple statements",
            sql: "SELECT value FROM first LIMIT 1; SELECT value FROM second OFFSET 1",
            expected_codes: &["SQBL004", "SQBL004"],
            expected_anchors: &[("SQBL004", "LIMIT"), ("SQBL004", "OFFSET")],
        },
        test_types::LintTestCase {
            description: "nested query anchors",
            sql: "SELECT * FROM (SELECT id FROM inner_items ORDER BY id LIMIT 1) safe JOIN outer_items ON TRUE OFFSET 2",
            expected_codes: &["SQBL003", "SQBL004"],
            expected_anchors: &[("SQBL003", "JOIN"), ("SQBL004", "OFFSET")],
        },
        test_types::LintTestCase {
            description: "safe NULL predicate",
            sql: "SELECT value FROM a WHERE value IS NULL",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "NULL inside function",
            sql: "SELECT value FROM a WHERE COALESCE(value, NULL) = 1",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "NULL assignment",
            sql: "UPDATE items SET value = NULL",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "cross join",
            sql: "SELECT a.id FROM a CROSS JOIN b",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "keyed join",
            sql: "SELECT a.id FROM a JOIN b ON a.id = b.id",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "ordered limit",
            sql: "SELECT id FROM items ORDER BY id LIMIT 1",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "used CTE",
            sql: "WITH used AS (SELECT 1 AS id) SELECT id FROM used",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "group without distinct",
            sql: "SELECT id FROM items GROUP BY id",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "nonredundant distinct",
            sql: "SELECT DISTINCT a FROM items GROUP BY a, b",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "within group",
            sql: "SELECT DISTINCT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) FROM items",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "explicit positional set",
            sql: "SELECT id FROM a UNION ALL SELECT id FROM b",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "nested star outside set arms",
            sql: "SELECT id, name FROM (SELECT * FROM base) b UNION ALL SELECT id, name FROM other",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "nested star inside wrapped set arm",
            sql: "(SELECT id FROM (SELECT * FROM base) b) UNION ALL (SELECT id FROM other)",
            expected_codes: &[],
            expected_anchors: &[],
        },
    ];

    for test_case in &test_cases {
        let diagnostics = helpers::diagnostics(test_case.sql)?;
        let codes: Vec<&str> = diagnostics
            .iter()
            .filter_map(|item| item["code"].as_str())
            .collect();
        let anchors: Vec<(&str, &str)> = diagnostics
            .iter()
            .filter_map(|item| {
                let code = item["code"].as_str()?;
                let start = item["start"].as_u64()? as usize;
                let end = item["end"].as_u64()? as usize;
                Some((code, &test_case.sql[start..end]))
            })
            .collect();
        assert_eq!(codes, test_case.expected_codes, "{}", test_case.description);
        for expected_anchor in test_case.expected_anchors {
            assert!(
                anchors.contains(expected_anchor),
                "{}",
                test_case.description
            );
        }
    }
    Ok(())
}

#[test]
fn given_format_cases_when_formatting_then_output_matches() -> Result<(), String> {
    let test_cases = [
        test_types::FormatTestCase {
            description: "comment-free canonical SQL",
            sql: "select a,b from items where a=1",
            expected_sql: "SELECT\n  a,\n  b\nFROM items\nWHERE\n  a = 1",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "block comment attachment",
            sql: "SELECT a, /* preserve */ b FROM items",
            expected_sql: "SELECT\n  a, /* preserve */\n  b\nFROM items",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "line and leading comments",
            sql: "-- lead\nselect a,b from items -- tail\nwhere a=1",
            expected_sql: "-- lead\nSELECT\n  a,\n  b\nFROM items -- tail\nWHERE\n  a = 1",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "comment marker string",
            sql: "select '-- not a comment' as value",
            expected_sql: "SELECT\n  '-- not a comment' AS value",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "trailing comment",
            sql: "select a from items; -- retained",
            expected_sql: "SELECT\n  a\nFROM items -- retained\n",
            expected_changed: true,
        },
    ];

    for test_case in &test_cases {
        let response = format_json(
            &json!({"version": 1, "sql": test_case.sql, "dialect": "snowflake"}).to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        assert_eq!(
            payload["changed"], test_case.expected_changed,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_unknown_rule_when_linting_then_request_is_rejected() -> Result<(), String> {
    let test_cases = [test_types::InvalidRuleTestCase {
        description: "unknown native lint rule",
        rule: "SQBL999",
        expected_message: "unknown native lint rule 'SQBL999'",
    }];

    for test_case in &test_cases {
        let request = json!({"version": 1, "sql": "SELECT 1", "dialect": "snowflake", "enabled_rules": [test_case.rule]}).to_string();
        let error = lint_json(&request)
            .err()
            .ok_or_else(|| "unknown rule should fail".to_string())?;
        assert!(
            error.contains(test_case.expected_message),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
