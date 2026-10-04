use std::time::Instant;

use serde_json::Value;

use crate::sql_quality::tests::helpers::{anchors, lint_dialect, wide_json_select};
use crate::sql_quality::tests::test_types::{JsonParseScaleTestCase, JsonParseTestCase};

const RULE: &str = "SQBRSQL045";

#[test]
fn given_json_parse_calls_when_linting_then_repeats_in_one_select_are_reported()
-> Result<(), String> {
    let test_cases = [
        JsonParseTestCase {
            description: "same column parsed twice reports the second call",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(e.value):order_id AS order_id, TRY_PARSE_JSON(e.value):status AS status FROM events AS e",
            expected_anchors: &["TRY_PARSE_JSON"],
            expected_details: &["TRY_PARSE_JSON(e.value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "the finding is located at the second call",
            dialect: "snowflake",
            sql: "SELECT try_parse_json(value):a AS a, TRY_PARSE_JSON(value):b AS b FROM events",
            expected_anchors: &["TRY_PARSE_JSON"],
            expected_details: &["TRY_PARSE_JSON(value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "three parses give one finding with the count",
            dialect: "snowflake",
            sql: "SELECT PARSE_JSON(value):a AS a, PARSE_JSON(value):b AS b FROM events WHERE PARSE_JSON(value):c IS NOT NULL",
            expected_anchors: &["PARSE_JSON"],
            expected_details: &["PARSE_JSON(value) is parsed 3 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "column casing and wrappers do not hide a repeat",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(LOWER(E.Value)):a AS a, TRY_PARSE_JSON((CAST(TRIM(e.value) AS VARCHAR))):b AS b, TRY_PARSE_JSON(COALESCE(UPPER(e.VALUE))):c AS c FROM events AS e",
            expected_anchors: &["TRY_PARSE_JSON"],
            expected_details: &["TRY_PARSE_JSON(e.value) is parsed 3 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "multi-argument COALESCE is not a plain column",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(COALESCE(e.value, e.backup)):a AS a, TRY_PARSE_JSON(COALESCE(e.value, e.fallback)):b AS b, TRY_PARSE_JSON(e.value):c AS c FROM events AS e",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "TRIM with characters is not a plain column",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(TRIM(e.value, ' ')):a AS a, TRY_PARSE_JSON(e.value):b AS b FROM events AS e",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "quoted names differing in case are different columns",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(e.\"Value\"):a AS a, TRY_PARSE_JSON(e.\"value\"):b AS b FROM events AS e",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "quoted and unquoted names are not merged",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(e.\"value\"):a AS a, TRY_PARSE_JSON(e.value):b AS b FROM events AS e",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "quoted qualifiers differing in case are different relations",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(\"E\".value):a AS a, TRY_PARSE_JSON(\"e\".value):b AS b FROM events AS \"E\" INNER JOIN events AS \"e\" ON \"E\".id = \"e\".id",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "identical quoted names are reported as written",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(\"E\".\"Value\"):a AS a, TRY_PARSE_JSON(\"E\".\"Value\"):b AS b FROM events AS \"E\"",
            expected_anchors: &["TRY_PARSE_JSON"],
            expected_details: &["TRY_PARSE_JSON(\"E\".\"Value\") is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "bigquery quoted names keep backticks",
            dialect: "bigquery",
            sql: "SELECT JSON_VALUE(PARSE_JSON(e.`Value`), '$.a') AS a, JSON_VALUE(PARSE_JSON(e.`Value`), '$.b') AS b FROM events AS e",
            expected_anchors: &["PARSE_JSON"],
            expected_details: &["PARSE_JSON(e.`Value`) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "snowflake quoted upper case matches the folded unquoted name",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(e.\"VALUE\"):a AS a, TRY_PARSE_JSON(e.value):b AS b FROM events AS e",
            expected_anchors: &["TRY_PARSE_JSON"],
            expected_details: &["TRY_PARSE_JSON(e.value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "duckdb quoted names are case-insensitive",
            dialect: "duckdb",
            sql: "SELECT json(e.\"Value\") -> 'a' AS a, json(e.value) -> 'b' AS b FROM events AS e",
            expected_anchors: &["json"],
            expected_details: &["JSON(e.value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "bigquery backticked names are case-insensitive",
            dialect: "bigquery",
            sql: "SELECT JSON_VALUE(PARSE_JSON(e.`Value`), '$.a') AS a, JSON_VALUE(PARSE_JSON(e.value), '$.b') AS b FROM events AS e",
            expected_anchors: &["PARSE_JSON"],
            expected_details: &["PARSE_JSON(e.value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "databricks backticked names are case-insensitive",
            dialect: "databricks",
            sql: "SELECT try_parse_json(e.`v`) AS a, try_parse_json(e.V) AS b FROM events AS e",
            expected_anchors: &["try_parse_json"],
            expected_details: &["TRY_PARSE_JSON(e.V) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "references are grouped as written",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(value):a AS a, TRY_PARSE_JSON(e.value):b AS b, TRY_PARSE_JSON(events.value):c AS c FROM events AS e",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "different columns pass",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(e.payload):a AS a, TRY_PARSE_JSON(e.metadata):b AS b FROM events AS e",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "same column name on different tables passes",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(o.payload):a AS a, TRY_PARSE_JSON(c.payload):b AS b FROM orders AS o INNER JOIN customers AS c ON o.customer_id = c.customer_id",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "different parse functions are not merged",
            dialect: "snowflake",
            sql: "SELECT PARSE_JSON(value):a AS a, TRY_PARSE_JSON(value):b AS b FROM events",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "one parse per CTE scope passes",
            dialect: "snowflake",
            sql: "WITH parsed AS (SELECT TRY_PARSE_JSON(value) AS payload FROM events), final AS (SELECT TRY_PARSE_JSON(value) AS payload FROM events) SELECT payload FROM final",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "nested SELECT is its own scope",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(e.value):a AS a, (SELECT MAX(TRY_PARSE_JSON(x.value):b) FROM events AS x) AS b FROM events AS e",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "repeat inside a subquery is reported in that scope",
            dialect: "snowflake",
            sql: "SELECT e.order_id FROM events AS e WHERE e.order_id IN (SELECT TRY_PARSE_JSON(value):id FROM events WHERE TRY_PARSE_JSON(value):ok)",
            expected_anchors: &["TRY_PARSE_JSON"],
            expected_details: &["TRY_PARSE_JSON(value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "union branches are separate scopes",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(value) AS payload FROM events UNION ALL SELECT TRY_PARSE_JSON(value) AS payload FROM events",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "a repeat inside one CTE body is reported",
            dialect: "snowflake",
            sql: "WITH parsed AS (SELECT TRY_PARSE_JSON(value):a AS a, TRY_PARSE_JSON(value):b AS b FROM events) SELECT a, b FROM parsed",
            expected_anchors: &["TRY_PARSE_JSON"],
            expected_details: &["TRY_PARSE_JSON(value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "non-column arguments pass",
            dialect: "snowflake",
            sql: "SELECT TRY_PARSE_JSON(value || '') AS a, TRY_PARSE_JSON(value || '') AS b FROM events",
            expected_anchors: &[],
            expected_details: &[],
        },
        JsonParseTestCase {
            description: "bigquery safe parse is matched",
            dialect: "bigquery",
            sql: "SELECT JSON_VALUE(SAFE.PARSE_JSON(e.value), '$.a') AS a, JSON_VALUE(SAFE.PARSE_JSON(e.value), '$.b') AS b FROM events AS e",
            expected_anchors: &["PARSE_JSON"],
            expected_details: &["SAFE.PARSE_JSON(e.value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "databricks try parse is matched",
            dialect: "databricks",
            sql: "SELECT try_parse_json(value) AS a, try_parse_json(value) AS b FROM events",
            expected_anchors: &["try_parse_json"],
            expected_details: &["TRY_PARSE_JSON(value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "duckdb json is matched",
            dialect: "duckdb",
            sql: "SELECT json(e.value)->>'a' AS a, json(e.value)->>'b' AS b FROM events AS e",
            expected_anchors: &["json"],
            expected_details: &["JSON(e.value) is parsed 2 times in one SELECT."],
        },
        JsonParseTestCase {
            description: "dialects without an equivalent are not checked",
            dialect: "postgres",
            sql: "SELECT CAST(value AS JSONB) AS a, CAST(value AS JSONB) AS b FROM events",
            expected_anchors: &[],
            expected_details: &[],
        },
    ];
    for test_case in &test_cases {
        let diagnostics: Vec<Value> = lint_dialect(test_case.sql, test_case.dialect, RULE)?;
        assert_eq!(
            anchors(test_case.sql, &diagnostics),
            test_case.expected_anchors,
            "{}",
            test_case.description
        );
        let details: Vec<String> = diagnostics
            .iter()
            .map(|diagnostic| {
                diagnostic["remediation"]
                    .as_str()
                    .unwrap_or_default()
                    .split_inclusive(". ")
                    .next()
                    .unwrap_or_default()
                    .trim_end()
                    .to_owned()
            })
            .collect();
        assert_eq!(
            details, test_case.expected_details,
            "{}",
            test_case.description
        );
        assert!(
            diagnostics
                .iter()
                .all(|diagnostic| diagnostic["fix"].is_null()),
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_wide_select_with_many_repeated_parses_when_linting_then_it_stays_linear()
-> Result<(), String> {
    let test_cases = [JsonParseScaleTestCase {
        description: "3,000 projections parsing 1,500 payload columns twice each",
        column_count: 1_500,
        expected_findings: 1_500,
        expected_max_seconds: 10.0,
    }];
    for test_case in &test_cases {
        let started: Instant = Instant::now();
        let diagnostics: Vec<Value> =
            lint_dialect(&wide_json_select(test_case.column_count), "duckdb", RULE)?;
        let elapsed: f64 = started.elapsed().as_secs_f64();
        assert_eq!(
            diagnostics.len(),
            test_case.expected_findings,
            "{}",
            test_case.description
        );
        assert!(
            elapsed <= test_case.expected_max_seconds,
            "{}: {elapsed:.2}s",
            test_case.description
        );
    }
    Ok(())
}
