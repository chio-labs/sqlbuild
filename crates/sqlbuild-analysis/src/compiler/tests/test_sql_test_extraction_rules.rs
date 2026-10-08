use crate::compiler::tests::helpers::{
    accepted_outcome, extraction_rule_outcome, rejected_outcome,
};
use serde_json::json;

use crate::compiler::tests::helpers::authored_ctes_response;
use crate::compiler::tests::test_types::{AuthoredCtesTestCase, ExtractionRuleTestCase};

const NAME_HELP: Option<&str> = Some(
    "rename the CTE, for example my_helper; quoted CTE names and names with $ or non-ASCII characters are not supported",
);

#[test]
fn given_authored_sql_tests_when_extracting_then_each_rule_holds() {
    let test_cases = [
        ExtractionRuleTestCase {
            description: "a double-quoted CTE name is rejected at its position",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH \"my helper\" AS (SELECT 1 AS a), __udf_actual__ AS (SELECT 1 AS a), __udf_expected__ AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' CTE name \"my helper\" must be an unquoted identifier of ASCII letters, digits and underscores",
                NAME_HELP,
                Some(("\"my helper\"", 5)),
            ),
        },
        ExtractionRuleTestCase {
            description: "a backtick CTE name is rejected",
            mode: "model",
            raw: false,
            syntax: "bigquery",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), `my helper` AS (SELECT 1 AS a), __expected__orders AS (SELECT 1 AS id)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' CTE name `my helper` must be an unquoted identifier of ASCII letters, digits and underscores",
                NAME_HELP,
                Some(("`my helper`", 40)),
            ),
        },
        ExtractionRuleTestCase {
            description: "a CTE name with $ is rejected whole",
            mode: "macro",
            raw: true,
            syntax: "generic",
            sql: "WITH my$helper AS (SELECT 1 AS a), __macro_actual__ AS (SELECT @m(1) AS a), __macro_expected__ AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' CTE name 'my$helper' must be an unquoted identifier of ASCII letters, digits and underscores",
                NAME_HELP,
                Some(("my$helper", 5)),
            ),
        },
        ExtractionRuleTestCase {
            description: "a non-ASCII CTE name is rejected with a code-point offset",
            mode: "udf",
            raw: false,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT 'é' AS a), helpér AS (SELECT 1 AS a), __udf_expected__ AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' CTE name 'helpér' must be an unquoted identifier of ASCII letters, digits and underscores",
                Some(
                    "rename the CTE, for example help_r; quoted CTE names and names with $ or non-ASCII characters are not supported",
                ),
                Some(("helpér", 42)),
            ),
        },
        ExtractionRuleTestCase {
            description: "keywords match ASCII case-insensitively only",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__ aſ (SELECT 1 AS a), __udf_expected__ AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' expected keyword AS",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "Python whitespace separates tokens and is stripped from bodies",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__\u{1c}AS (SELECT __udf(\"f\")(1) AS a\u{1c}), __udf_expected__\u{a0}AS (SELECT 1 AS a)",
            expected_outcome: accepted_outcome(false),
        },
        ExtractionRuleTestCase {
            description: "a UDF call followed by a no-break space in an expected CTE does not panic",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT __udf(\"f\")(1) AS a), __udf_expected__ AS (SELECT __udf\u{a0}(\"f\")(1))",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must alias every non-trivial __udf_expected__ projection",
                Some(
                    "name the column with an alias, for example __udf\u{a0}(\"f\")(1) AS <name>; only a bare or qualified column reference may go unaliased",
                ),
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "an implicit alias needs AS",
            mode: "model",
            raw: false,
            syntax: "generic",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), __expected__orders AS (SELECT a IS NULL) SELECT 1",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must alias every non-trivial __expected__orders projection",
                Some(
                    "name the column with an alias, for example a IS NULL AS <name>; only a bare or qualified column reference may go unaliased",
                ),
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "implicit aliases name literals, casts and quoted columns",
            mode: "model",
            raw: false,
            syntax: "generic",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), __expected__orders AS (SELECT 1 order_id, CAST(100 AS INTEGER) customer_id, 'x' \"Status\", x::int amount, CASE WHEN a THEN 1 END /* c */ flag, a IS NULL missing) SELECT 1",
            expected_outcome: accepted_outcome(false),
        },
        ExtractionRuleTestCase {
            description: "a trailing value keyword is not an implicit alias",
            mode: "model",
            raw: false,
            syntax: "generic",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), __expected__orders AS (SELECT CASE WHEN a THEN 1 END) SELECT 1",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must alias every non-trivial __expected__orders projection",
                Some(
                    "name the column with an alias, for example CASE WHEN a THEN 1 END AS <name>; only a bare or qualified column reference may go unaliased",
                ),
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "a token after an operator keyword is an operand, not an implicit alias",
            mode: "udf",
            raw: false,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT 1 AS a), __udf_expected__ AS (SELECT x BETWEEN 1 AND y)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must alias every non-trivial __udf_expected__ projection",
                Some(
                    "name the column with an alias, for example x BETWEEN 1 AND y AS <name>; only a bare or qualified column reference may go unaliased",
                ),
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "a token after an operator character is an operand, not an implicit alias",
            mode: "udf",
            raw: false,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT 1 AS a), __udf_expected__ AS (SELECT a + b)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must alias every non-trivial __udf_expected__ projection",
                Some(
                    "name the column with an alias, for example a + b AS <name>; only a bare or qualified column reference may go unaliased",
                ),
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "bare, qualified and DISTINCT column references go unaliased",
            mode: "model",
            raw: false,
            syntax: "generic",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), __expected__orders AS (SELECT DISTINCT o.id, \"Status\", s.t.amount FROM __ref__orders o) SELECT 1",
            expected_outcome: accepted_outcome(false),
        },
        ExtractionRuleTestCase {
            description: "a qualified star is SELECT *",
            mode: "model",
            raw: false,
            syntax: "generic",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), __expected__orders AS (SELECT o.* FROM __ref__orders o)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must not use SELECT * in __expected__orders CTEs",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "SELECT DISTINCT * is SELECT *",
            mode: "udf",
            raw: false,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT 1 AS a), __udf_expected__ AS (SELECT DISTINCT * FROM h), h AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must not use SELECT * in __udf_expected__ CTEs",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "parenthesised expected branches are rejected",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT 1 AS a), __udf_expected__ AS ((SELECT 1 AS a) UNION ALL (SELECT 2 AS a))",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must write each __udf_expected__ set-operation branch as a plain SELECT without enclosing parentheses",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "WITH inside an expected CTE is rejected with help",
            mode: "model",
            raw: false,
            syntax: "generic",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), __expected__orders AS (WITH rows_in AS (SELECT 1 AS id) SELECT id FROM rows_in)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must not use WITH inside __expected__orders",
                Some(
                    "define the shared rows as a helper CTE in the test's top-level WITH clause and select from it",
                ),
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "a macro-test helper may not call a UDF",
            mode: "macro",
            raw: true,
            syntax: "generic",
            sql: "WITH h AS (SELECT __udf(\"f\")(1) AS a), __macro_actual__ AS (SELECT @m(1) AS a), __macro_expected__ AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' mode 'macro' helper CTE 'h' must not call udf; call reusable logic only in __macro_actual__",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "the first logic call in text order names the kind",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT 1 AS a), __udf_expected__ AS (SELECT __table_fn(\"t\")(1) + __udf(\"f\")(1) AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' mode 'udf' CTE __udf_expected__ must not call table_fn; call reusable logic only in __udf_actual__",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "malformed reference calls are flagged for P012 instead of read as logic calls",
            mode: "table_fn",
            raw: true,
            syntax: "generic",
            sql: "WITH h AS (SELECT * FROM __table_fn(\"t\")), __table_fn_actual__ AS (SELECT * FROM __table_fn(\"t\")(1)), __table_fn_expected__ AS (SELECT __source(\"s\", \"t\") AS a)",
            expected_outcome: accepted_outcome(true),
        },
        ExtractionRuleTestCase {
            description: "a raw helper calling a macro names the allowed location",
            mode: "macro",
            raw: true,
            syntax: "generic",
            sql: "WITH h AS (SELECT @tidy(a) AS a), __macro_actual__ AS (SELECT @m(1) AS a), __macro_expected__ AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' mode 'macro' helper CTE 'h' must not call macros; call macros only in __macro_actual__",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "raw macro detection counts @var but not declaration calls",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT __udf(\"f\")(1) AS a), __udf_expected__ AS (SELECT @var('x') AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' mode 'udf' CTE __udf_expected__ must not call macros",
                None,
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "raw macro detection skips enum and const and their arguments",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT __udf(\"f\")(1) AS a), __udf_expected__ AS (SELECT @enum('Status', 'PAID') AS a, @const(@m(1)) AS b)",
            expected_outcome: accepted_outcome(false),
        },
        ExtractionRuleTestCase {
            description: "BigQuery hash comments hide calls and parentheses",
            mode: "udf",
            raw: true,
            syntax: "bigquery",
            sql: "WITH __udf_actual__ AS (SELECT __udf(\"f\")(1) AS a), # __udf(\"g\")(1) ),\n__udf_expected__ AS (SELECT 'it\\'s' AS a # __udf(\"g\")(\n)",
            expected_outcome: accepted_outcome(false),
        },
        ExtractionRuleTestCase {
            description: "DuckDB nested comments and E-strings follow DuckDB rules",
            mode: "udf",
            raw: true,
            syntax: "duckdb",
            sql: "WITH __udf_actual__ AS (SELECT __udf(\"f\")(1) AS a /* x /* ) */ */), __udf_expected__ AS (SELECT E'\\'' AS a)",
            expected_outcome: accepted_outcome(false),
        },
        ExtractionRuleTestCase {
            description: "generic rules end a block comment at its first close",
            mode: "udf",
            raw: true,
            syntax: "generic",
            sql: "WITH __udf_actual__ AS (SELECT 1 AS a), __udf_expected__ AS (SELECT 1 AS a /* x /* y */ */)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' must alias every non-trivial __udf_expected__ projection",
                Some(
                    "name the column with an alias, for example 1 AS a /* x /* y */ */ AS <name>; only a bare or qualified column reference may go unaliased",
                ),
                None,
            ),
        },
        ExtractionRuleTestCase {
            description: "a UDF-test CTE in a model test names the UDF mode",
            mode: "model",
            raw: false,
            syntax: "generic",
            sql: "WITH __ref__orders AS (SELECT 1 AS id), __udf_actual__ AS (SELECT 1 AS a)",
            expected_outcome: rejected_outcome(
                "SQL test 'tests/t.sql' is mode 'model' but defines UDF-test CTE '__udf_actual__'; use TEST (mode udf)",
                None,
                None,
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            extraction_rule_outcome(&test_case),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_authored_blocks_when_reading_ctes_then_offsets_and_name_errors_are_exact() {
    let test_cases = [
        AuthoredCtesTestCase {
            description: "body offsets count code points and skip leading whitespace",
            sql: "-- café\nWITH h AS (  SELECT 'é' AS a), __ref__orders AS (\n SELECT 1)",
            expected_response: json!({"tests": [{"kind": "authored", "ctes": [
                ["h", 21, "SELECT 'é' AS a"],
                ["__ref__orders", 59, "SELECT 1"],
            ]}]}),
        },
        AuthoredCtesTestCase {
            description: "a CTE name error keeps its code-point offset",
            sql: "-- é\nWITH h AS (SELECT 1), café AS (SELECT 2)",
            expected_response: json!({"error": {
                "index": 0,
                "message": "SQL test 'tests/t.sql' CTE name 'café' must be an unquoted identifier of ASCII letters, digits and underscores",
                "help": "rename the CTE, for example caf_; quoted CTE names and names with $ or non-ASCII characters are not supported",
                "token": "café",
                "tokenOffset": 27,
            }}),
        },
        AuthoredCtesTestCase {
            description: "other errors are left to extraction and read as no CTEs",
            sql: "WITH h AS (SELECT 1) SELECT * FROM h",
            expected_response: json!({"tests": [{"kind": "authored", "ctes": []}]}),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            authored_ctes_response(test_case.sql),
            test_case.expected_response,
            "{}",
            test_case.description
        );
    }
}
