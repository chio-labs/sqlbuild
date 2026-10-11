//! Classification cases moved from the deleted Python wrapper tests, with exact outcomes.

use crate::sql_test_attachment::tests::helpers::{
    assertion_targets, batch_outcome, parity_payload, scenario_outcome,
};
use crate::sql_test_attachment::tests::test_types::{
    AssertionTargetsTestCase, BatchClassificationTestCase, ExtractionParityTestCase,
    ScenarioClassificationTestCase,
};

#[test]
fn given_sql_test_blocks_when_classifying_then_outcomes_are_exact() {
    let test_cases = [
        BatchClassificationTestCase {
            description: "model roles: extracts dbt ref mocks from dbt ref prefixed ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __dbt_ref__orders AS (SELECT 1 AS order_id),\n        __dbt_ref__stripe__payments AS (SELECT 1 AS payment_id),\n        __expected__fact_orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__dbt_ref__orders","SELECT 1 AS order_id"],["__dbt_ref__stripe__payments","SELECT 1 AS payment_id"]],"macroMocks":[],"mockModels":[],"mockSources":[],"mockSeeds":[],"mockDbtRefs":["orders","stripe__payments"],"mockTableFunctions":[],"expected":[["__expected__fact_orders","SELECT 1 AS order_id"]],"expectedModels":["fact_orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts model ctes when the trailing select is omitted",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts model ctes ending with a semicolon and comment",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id);\n        -- end of test", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts table function fixtures from model tests",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __table_fn__customer_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__table_fn__customer_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":["customer_orders"],"expected":[["__expected__orders","SELECT 1 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: allows empty fixture marker for model expected output",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT * FROM __empty_fixture())\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT * FROM __empty_fixture()"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts zero-row assertion ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id, 10 AS amount),\n        __assert__no_negative_orders AS (\n          SELECT * FROM __ref(\"orders\") WHERE amount < 0\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id, 10 AS amount"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[],"expectedModels":[],"assertions":[["__assert__no_negative_orders","SELECT * FROM __ref(\"orders\") WHERE amount < 0"]],"assertionNames":["no_negative_orders"]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts mixed expected and assertion ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id, 10 AS amount),\n        __expected__orders AS (SELECT 1 AS order_id, 10 AS amount),\n        __assert__no_negative_orders AS (\n          SELECT * FROM __ref(\"orders\") WHERE amount < 0\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id, 10 AS amount"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id, 10 AS amount"]],"expectedModels":["orders"],"assertions":[["__assert__no_negative_orders","SELECT * FROM __ref(\"orders\") WHERE amount < 0"]],"assertionNames":["no_negative_orders"]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: allows expected result and assertion to share an independent helper",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        helper AS (SELECT 1 AS order_id),\n        __source__raw_orders AS (SELECT order_id FROM helper),\n        __expected__orders AS (SELECT order_id FROM helper),\n        __assert__positive_order_id AS (SELECT order_id FROM helper WHERE order_id < 1)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["helper","SELECT 1 AS order_id"],["__source__raw_orders","SELECT order_id FROM helper"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT order_id FROM helper"]],"expectedModels":["orders"],"assertions":[["__assert__positive_order_id","SELECT order_id FROM helper WHERE order_id < 1"]],"assertionNames":["positive_order_id"]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts seed mocks from seed-prefixed ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __seed__country_codes AS (SELECT 'US' AS country_code),\n        __expected__orders AS (SELECT 'US' AS country_code)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__seed__country_codes","SELECT 'US' AS country_code"]],"macroMocks":[],"mockModels":[],"mockSources":[],"mockSeeds":["country_codes"],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 'US' AS country_code"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts macro mocks from single string literal ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __macro__country AS (SELECT '''US'''),\n        __macro__empty AS (SELECT ''),\n        __macro__literal_text AS (SELECT ''' + x + '''),\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[["country","'US'"],["empty",""],["literal_text","' + x + '"]],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts ctes from compact single line test sql",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        helper AS (SELECT 1 AS order_id),\n        __ref__orders AS (SELECT * FROM helper),\n        __expected__order_items AS (SELECT order_id FROM __ref__orders)\n        SELECT 1;", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["helper","SELECT 1 AS order_id"],["__ref__orders","SELECT * FROM helper"]],"macroMocks":[],"mockModels":["orders"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__order_items","SELECT order_id FROM __ref__orders"]],"expectedModels":["order_items"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts ctes with comments strings and nested parentheses",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH /* leading */ helper_orders(order_id, note) AS (\n          SELECT\n            CAST('value ) inside string' AS VARCHAR) AS note,\n            COALESCE(order_id, 0) AS order_id\n          FROM raw_orders -- comment with ) and ,\n        ) ,\n        __source__raw_orders AS (SELECT * FROM helper_orders),\n        __expected__orders AS (\n          SELECT order_id, note FROM __source__raw_orders WHERE note != 'not ) done'\n        )\n        -- final comment before ceremonial select\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["helper_orders","SELECT\n            CAST('value ) inside string' AS VARCHAR) AS note,\n            COALESCE(order_id, 0) AS order_id\n          FROM raw_orders -- comment with ) and ,"],["__source__raw_orders","SELECT * FROM helper_orders"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT order_id, note FROM __source__raw_orders WHERE note != 'not ) done'"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts multiple expected targets with mixed whitespace",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS(SELECT 1 AS order_id),__expected__orders AS(\n          SELECT 1 AS order_id\n        ),\n        __expected__daily_revenue AS (SELECT SUM(1) AS revenue)\n        SELECT 1;", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id"],["__expected__daily_revenue","SELECT SUM(1) AS revenue"]],"expectedModels":["orders","daily_revenue"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts ctes through nested helper chains and awkward comma placement",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH source_seed(seed_id, payload) AS (\n          SELECT * FROM (\n            SELECT 1 AS seed_id, 'a,b,c' AS payload\n            UNION ALL\n            SELECT 2 AS seed_id, 'literal with ) and , chars' AS payload\n          ) AS nested_seed\n        )/* comma after block comment */,\n        normalized_orders AS(\n          SELECT seed_id AS order_id, CONCAT(payload, ')') AS note FROM source_seed\n        )\n        ,__source__raw_orders AS(\n          SELECT * FROM normalized_orders WHERE note NOT IN ('x,y', 'z)')\n        ), expected_rows AS (\n          SELECT order_id, note FROM __source__raw_orders\n          WHERE order_id IN (SELECT seed_id FROM source_seed WHERE seed_id > 0)\n        ),\n        __expected__orders AS (SELECT order_id, note FROM expected_rows)\n        SELECT 1;", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["source_seed","SELECT * FROM (\n            SELECT 1 AS seed_id, 'a,b,c' AS payload\n            UNION ALL\n            SELECT 2 AS seed_id, 'literal with ) and , chars' AS payload\n          ) AS nested_seed"],["normalized_orders","SELECT seed_id AS order_id, CONCAT(payload, ')') AS note FROM source_seed"],["__source__raw_orders","SELECT * FROM normalized_orders WHERE note NOT IN ('x,y', 'z)')"],["expected_rows","SELECT order_id, note FROM __source__raw_orders\n          WHERE order_id IN (SELECT seed_id FROM source_seed WHERE seed_id > 0)"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT order_id, note FROM expected_rows"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: extracts ctes with inline comments around separators",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH helper_a AS (SELECT 1 AS order_id) -- comment before comma\n        , helper_b AS (SELECT order_id FROM helper_a /* ) , */)\n        , __ref__orders AS (SELECT order_id FROM helper_b), -- trailing comma comment\n        __expected__orders AS (\n          SELECT order_id FROM __ref__orders WHERE order_id = (SELECT MAX(order_id) FROM helper_b)\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["helper_a","SELECT 1 AS order_id"],["helper_b","SELECT order_id FROM helper_a /* ) , */"],["__ref__orders","SELECT order_id FROM helper_b"]],"macroMocks":[],"mockModels":["orders"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT order_id FROM __ref__orders WHERE order_id = (SELECT MAX(order_id) FROM helper_b)"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: allows explicit union branches in expected ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (\n          SELECT 1 AS order_id, 'new' AS status\n        ),\n        __expected__orders AS (\n          SELECT 1 AS order_id, 'new' AS status\n          UNION ALL\n          SELECT 2 AS order_id, 'paid' AS status\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id, 'new' AS status"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id, 'new' AS status\n          UNION ALL\n          SELECT 2 AS order_id, 'paid' AS status"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: allows plain union with matching aliases in expected ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (\n          SELECT 1 AS order_id, 'created' AS status\n          UNION\n          SELECT 2 AS order_id, 'paid' AS status\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id, 'created' AS status\n          UNION\n          SELECT 2 AS order_id, 'paid' AS status"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: allows cast expressions with explicit aliases in expected ctes",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (\n          SELECT\n            CAST(1 AS INTEGER) AS order_id,\n            CAST('paid' AS VARCHAR) AS status\n          UNION ALL\n          SELECT\n            CAST(2 AS INTEGER) AS order_id,\n            CAST('created' AS VARCHAR) AS status\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT\n            CAST(1 AS INTEGER) AS order_id,\n            CAST('paid' AS VARCHAR) AS status\n          UNION ALL\n          SELECT\n            CAST(2 AS INTEGER) AS order_id,\n            CAST('created' AS VARCHAR) AS status"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "model roles: allows bare identifiers in expected cte projections",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH expected_rows AS (SELECT 1 AS order_id, 'paid' AS status),\n        __source__raw_orders AS (SELECT * FROM expected_rows),\n        __expected__orders AS (\n          SELECT order_id, status FROM expected_rows\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["expected_rows","SELECT 1 AS order_id, 'paid' AS status"],["__source__raw_orders","SELECT * FROM expected_rows"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT order_id, status FROM expected_rows"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "direct roles: extracts unsuffixed macro actual expected ctes in macro mode",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH input_values AS (SELECT '  PAID  ' AS raw_status),\n        __macro_actual__ AS (\n          SELECT @normalize_status(\"raw_status\") AS status FROM input_values\n        ),\n        __macro_expected__ AS (SELECT 'paid' AS status)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[["input_values","SELECT '  PAID  ' AS raw_status"]],"actual":["__macro_actual__","SELECT @normalize_status(\"raw_status\") AS status FROM input_values"],"expected":["__macro_expected__","SELECT 'paid' AS status"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "direct roles: extracts unsuffixed udf actual expected ctes in udf mode",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH input_values AS (SELECT 1250 AS amount_cents),\n        __udf_actual__ AS (\n          SELECT __udf(\"format_cents\")(amount_cents) AS formatted FROM input_values\n        ),\n        __udf_expected__ AS (SELECT '$12.50' AS formatted)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[["input_values","SELECT 1250 AS amount_cents"]],"actual":["__udf_actual__","SELECT __udf(\"format_cents\")(amount_cents) AS formatted FROM input_values"],"expected":["__udf_expected__","SELECT '$12.50' AS formatted"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "direct roles: extracts unsuffixed table function actual expected ctes in table_fn mode",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (\n          SELECT customer_id, order_id FROM __table_fn(\"customer_orders\")(42)\n        ),\n        __table_fn_expected__ AS (SELECT 42 AS customer_id, 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT customer_id, order_id FROM __table_fn(\"customer_orders\")(42)"],"expected":["__table_fn_expected__","SELECT 42 AS customer_id, 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "direct roles: extracts macro ctes when the trailing select is omitted",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT @double(2) AS value),\n        __macro_expected__ AS (SELECT 4 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT @double(2) AS value"],"expected":["__macro_expected__","SELECT 4 AS value"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when ceremonial select is wrapped in a final result cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id),\n        test_result AS (SELECT 1)\n        SELECT * FROM test_result", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when assertion depends directly on expected result",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id),\n        __assert__expected_is_nonempty AS (SELECT * FROM __expected__orders)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' check CTE '__assert__expected_is_nonempty' must not depend on '__expected__orders'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when unparsed assertion uses quoted expected result",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id),\n        __assert__expected_is_nonempty AS (\n          SELECT @normalize_order(order_id) FROM \"__expected__orders\"\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' check CTE '__assert__expected_is_nonempty' must not depend on '__expected__orders'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when assertion defines a shadowing expected result",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id),\n        __assert__empty AS (\n          WITH __expected__orders AS (SELECT 2 AS order_id)\n          SELECT * FROM __expected__orders WHERE order_id < 0\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' check CTE '__assert__empty' must not define expected result CTE '__expected__orders'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when lone assertion defines a nested expected result",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __assert__empty AS (\n          WITH __expected__orders AS (SELECT 2 AS order_id)\n          SELECT order_id FROM __expected__orders WHERE order_id < 0\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' check CTE '__assert__empty' must not define expected result CTE '__expected__orders'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when expected result depends directly on assertion",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __assert__positive_order_id AS (SELECT 1 AS order_id WHERE 1 < 1),\n        __expected__orders AS (SELECT order_id FROM __assert__positive_order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' check CTE '__expected__orders' must not depend on '__assert__positive_order_id'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when assertion depends indirectly on expected result",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id),\n        expected_helper AS (SELECT * FROM __expected__orders),\n        __assert__expected_is_nonempty AS (SELECT * FROM expected_helper)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' check CTE '__assert__expected_is_nonempty' must not depend on '__expected__orders' through 'expected_helper'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when macro mock returns multiple columns",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro__country AS (SELECT 'US', 'CA'),\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' macro mock '__macro__country' must be a single SELECT string literal with no FROM, UNION, or additional columns","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when macro mock returns non string literal",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro__country AS (SELECT 123),\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' macro mock '__macro__country' must be a single SELECT string literal, for example SELECT '''US'''","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when macro mock reads from a table",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro__country AS (SELECT 'US' FROM values_table),\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' macro mock '__macro__country' must be a single SELECT string literal with no FROM, UNION, or additional columns","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when macro mock uses union",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro__country AS (SELECT 'US' UNION ALL SELECT 'CA'),\n        __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' macro mock '__macro__country' must be a single SELECT string literal with no FROM, UNION, or additional columns","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when test sql does not start with top level with",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must declare mock CTEs and one __expected__<model> CTE in a top-level WITH clause","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when assertion cte omits assertion name",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1), __assert__ AS (SELECT 1)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use __assert__<assertion> to identify a target","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when cte body is unclosed",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id,\n        __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test contains an unclosed parenthesis","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when final select is not ceremonial select one",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1), __expected__orders AS (SELECT 1 AS order_id)\n        SELECT 1 FROM __expected__orders", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when final result cte is not ceremonial select one",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        __source__raw_orders AS (SELECT 1),\n        __expected__orders AS (SELECT 1),\n        test_result AS (SELECT 2)\n        SELECT * FROM test_result", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when fallback terminal read follows a set operation",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        \"__source__raw_orders\" AS (SELECT 1),\n        \"__expected__orders\" AS (SELECT 1),\n        test_result AS (SELECT 1)\n        SELECT 2 UNION ALL SELECT * FROM test_result", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' CTE name \"__source__raw_orders\" must be an unquoted identifier of ASCII letters, digits and underscores","help":"rename the CTE, for example __source__raw_orders; quoted CTE names and names with $ or non-ASCII characters are not supported","token":"\"__source__raw_orders\"","tokenOffset":13}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises for quoted CTE names instead of re-parsing the test",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n        \"__source__raw_orders\" AS MATERIALIZED (SELECT 1 AS order_id),\n        \"__expected__orders\" AS (SELECT order_id FROM \"__source__raw_orders\")\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' CTE name \"__source__raw_orders\" must be an unquoted identifier of ASCII letters, digits and underscores","help":"rename the CTE, for example __source__raw_orders; quoted CTE names and names with $ or non-ASCII characters are not supported","token":"\"__source__raw_orders\"","tokenOffset":13}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises for materialized CTEs",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS MATERIALIZED (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT order_id FROM __source__raw_orders)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' CTE '__source__raw_orders' must not use AS MATERIALIZED; materialization hints are not supported in SQL test CTEs","help":"remove MATERIALIZED and write __source__raw_orders AS (...)","token":"MATERIALIZED","tokenOffset":29}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when expected cte omits target name",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1), __expected__ AS (SELECT 1)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use __expected__<model> to identify a target","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when expected cte uses select star",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT * FROM __source__raw_orders)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must not use SELECT * in __expected__orders CTEs","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: rejects empty fixture marker for direct logic expected output",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 'paid' AS status),\n        __macro_expected__ AS (SELECT * FROM __empty_fixture())\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must not use SELECT * in __macro_expected__ CTEs","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when union branch projection order differs",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (\n          SELECT 1 AS order_id, 'paid' AS status\n          UNION ALL\n          SELECT 'created' AS status, 2 AS order_id\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __expected__orders projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when union branch projection alias is missing",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (\n          SELECT CAST(1 AS INTEGER) AS order_id, CAST('paid' AS VARCHAR) AS status\n          UNION ALL\n          SELECT CAST(2 AS INTEGER), CAST('created' AS VARCHAR) AS status\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must alias every non-trivial __expected__orders projection","help":"name the column with an alias, for example CAST(2 AS INTEGER) AS <name>; only a bare or qualified column reference may go unaliased","token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when non union projection alias is missing",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (\n          SELECT CAST(1 AS INTEGER), CAST('paid' AS VARCHAR) AS status\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must alias every non-trivial __expected__orders projection","help":"name the column with an alias, for example CAST(1 AS INTEGER) AS <name>; only a bare or qualified column reference may go unaliased","token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when expected branch is not a select query",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (\n          SELECT 1 AS order_id\n          UNION ALL\n          VALUES (2)\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must define each __expected__orders set-operation branch as a SELECT query","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when model mode includes macro actual cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT @normalize_status('paid') AS status),\n        __macro_expected__ AS (SELECT 'paid' AS status)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'model' but defines macro-test CTE '__macro_actual__'; use TEST (mode macro)","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when model mode includes udf actual cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT __udf(\"format_cents\")(1250) AS formatted),\n        __udf_expected__ AS (SELECT '$12.50' AS formatted)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'model' but defines UDF-test CTE '__udf_actual__'; use TEST (mode udf)","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when model mode includes table function actual cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT * FROM __table_fn(\"customer_orders\")(42)),\n        __table_fn_expected__ AS (SELECT 42 AS customer_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'model' but defines table_fn-test CTE '__table_fn_actual__'; use TEST (mode table_fn)","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when macro mode includes model test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __macro_actual__ AS (SELECT @normalize_status('paid') AS status),\n        __macro_expected__ AS (SELECT 'paid' AS status)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'macro' but defines model-test CTE '__source__raw_orders'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when macro expected calls macro",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT @normalize_status('paid') AS status),\n        __macro_expected__ AS (SELECT @normalize_status('paid') AS status)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'macro' CTE __macro_expected__ must not call macros","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when macro helper calls macro",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH helper AS (SELECT @normalize_status('paid') AS status),\n        __macro_actual__ AS (SELECT status FROM helper),\n        __macro_expected__ AS (SELECT 'paid' AS status)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'macro' helper CTE 'helper' must not call macros; call macros only in __macro_actual__","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when udf mode includes model test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id),\n        __udf_actual__ AS (SELECT __udf(\"format_cents\")(1250) AS formatted),\n        __udf_expected__ AS (SELECT '$12.50' AS formatted)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'udf' but defines model-test CTE '__source__raw_orders'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when udf expected calls udf",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT __udf(\"format_cents\")(1250) AS formatted),\n        __udf_expected__ AS (SELECT __udf(\"format_cents\")(1250) AS formatted)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'udf' CTE __udf_expected__ must not call udf; call reusable logic only in __udf_actual__","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when udf helper calls udf",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH helper AS (SELECT __udf(\"format_cents\")(1250) AS formatted),\n        __udf_actual__ AS (SELECT formatted FROM helper),\n        __udf_expected__ AS (SELECT '$12.50' AS formatted)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'udf' helper CTE 'helper' must not call udf; call reusable logic only in __udf_actual__","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when table function expected calls table function",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT * FROM __table_fn(\"customer_orders\")(42)),\n        __table_fn_expected__ AS (\n          SELECT customer_id FROM __table_fn(\"customer_orders\")(42)\n        )\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'table_fn' CTE __table_fn_expected__ must not call table_fn; call reusable logic only in __table_fn_actual__","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "invalid: raises when table function helper calls table function",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH helper AS (SELECT * FROM __table_fn(\"customer_orders\")(42)),\n        __table_fn_actual__ AS (SELECT * FROM helper),\n        __table_fn_expected__ AS (SELECT 42 AS customer_id)\n        SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'table_fn' helper CTE 'helper' must not call table_fn; call reusable logic only in __table_fn_actual__","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "malformed: sql test without a with clause keeps sql test wording",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "SELECT * FROM orders", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must declare mock CTEs and one __expected__<model> CTE in a top-level WITH clause","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "malformed: sql test with an invalid cte name keeps sql test wording",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH 1orders AS (SELECT 1) SELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' CTE name '1orders' must be an unquoted identifier of ASCII letters, digits and underscores","help":"rename the CTE, for example cte_1orders; quoted CTE names and names with $ or non-ASCII characters are not supported","token":"1orders","tokenOffset":5}}"####,
        },
        BatchClassificationTestCase {
            description: "malformed: sql test without a ceremonial select keeps sql test wording",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id), result AS (SELECT 1) SELECT * FROM result", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "independence: a check reading an expected CTE through a helper",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id), helper AS (SELECT order_id FROM __expected__orders), __assert__same AS (SELECT order_id FROM helper) SELECT 1", "fileLabel": "tests/unit/example.sql", "mode": "model"}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/example.sql' check CTE '__assert__same' must not depend on '__expected__orders' through 'helper'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "independence: a check joining an expected CTE in a comma-separated FROM",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__orders AS (SELECT 1 AS id), __expected__orders AS (SELECT 1 AS id), __assert__valid AS (SELECT expected.id FROM __source__orders source, __expected__orders expected) SELECT 1", "fileLabel": "tests/unit/example.sql", "mode": "model"}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/example.sql' check CTE '__assert__valid' must not depend on '__expected__orders'; expected results and assertions must be independent","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "dialect: snowflake backslash-escaped quote before a marker",
            request: r####"{"syntax": {"backslashEscapeQuotes": ["'"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--", "//"]}, "tests": [{"sql": "WITH\n__ref__stg_orders AS (SELECT 'O\\'Brien), (' AS customer_name),\n__assert__named AS (\n  SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model"}, {"sql": "WITH __ref__a AS (SELECT 1 AS id), __expected__b AS (SELECT 1 AS id) SELECT 1", "fileLabel": "tests/unit/plain.sql", "mode": "model"}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__ref__stg_orders","SELECT 'O\\'Brien), (' AS customer_name"]],"macroMocks":[],"mockModels":["stg_orders"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[],"expectedModels":[],"assertions":[["__assert__named","SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"assertionNames":["named"]},{"kind":"model","mode":"model","authored":[["__ref__a","SELECT 1 AS id"]],"macroMocks":[],"mockModels":["a"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__b","SELECT 1 AS id"]],"expectedModels":["b"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "dialect: bigquery hash comment and triple quotes around markers",
            request: r####"{"syntax": {"backslashEscapeQuotes": ["\"", "'", "`"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": true, "nestedBlockComments": false, "lineCommentPrefixes": ["#", "--"]}, "tests": [{"sql": "WITH\n__ref__stg_orders AS (SELECT '''it's ), (''' AS note), # ), (\n__assert__named AS (\n  SELECT * FROM __ref(\"order_totals\") # __ref(\"ignored\")\n)\nSELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model"}, {"sql": "WITH __ref__a AS (SELECT 1 AS id), __expected__b AS (SELECT 1 AS id) SELECT 1", "fileLabel": "tests/unit/plain.sql", "mode": "model"}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__ref__stg_orders","SELECT '''it's ), (''' AS note"]],"macroMocks":[],"mockModels":["stg_orders"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[],"expectedModels":[],"assertions":[["__assert__named","SELECT * FROM __ref(\"order_totals\") # __ref(\"ignored\")"]],"assertionNames":["named"]},{"kind":"model","mode":"model","authored":[["__ref__a","SELECT 1 AS id"]],"macroMocks":[],"mockModels":["a"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__b","SELECT 1 AS id"]],"expectedModels":["b"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "dialect: databricks backslash-escaped quote before a marker",
            request: r####"{"syntax": {"backslashEscapeQuotes": ["\"", "'"], "escapeStringPrefix": false, "rawStringPrefix": true, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n__ref__stg_orders AS (SELECT 'O\\'Brien), (' AS customer_name),\n__assert__named AS (\n  SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model"}, {"sql": "WITH __ref__a AS (SELECT 1 AS id), __expected__b AS (SELECT 1 AS id) SELECT 1", "fileLabel": "tests/unit/plain.sql", "mode": "model"}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__ref__stg_orders","SELECT 'O\\'Brien), (' AS customer_name"]],"macroMocks":[],"mockModels":["stg_orders"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[],"expectedModels":[],"assertions":[["__assert__named","SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"assertionNames":["named"]},{"kind":"model","mode":"model","authored":[["__ref__a","SELECT 1 AS id"]],"macroMocks":[],"mockModels":["a"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__b","SELECT 1 AS id"]],"expectedModels":["b"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "dialect: duckdb escape string and nested comment before a marker",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n__ref__stg_orders AS (SELECT E'O\\'Brien), (' AS customer_name),\n/* outer /* inner */ ), ( */\n__assert__named AS (\n  SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model"}, {"sql": "WITH __ref__a AS (SELECT 1 AS id), __expected__b AS (SELECT 1 AS id) SELECT 1", "fileLabel": "tests/unit/plain.sql", "mode": "model"}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__ref__stg_orders","SELECT E'O\\'Brien), (' AS customer_name"]],"macroMocks":[],"mockModels":["stg_orders"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[],"expectedModels":[],"assertions":[["__assert__named","SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"assertionNames":["named"]},{"kind":"model","mode":"model","authored":[["__ref__a","SELECT 1 AS id"]],"macroMocks":[],"mockModels":["a"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__b","SELECT 1 AS id"]],"expectedModels":["b"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "dialect: postgres escape string before a marker",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH\n__ref__stg_orders AS (SELECT E'O\\'Brien), (' AS customer_name),\n__assert__named AS (\n  SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1", "fileLabel": "tests/unit/orders.sql", "mode": "model"}, {"sql": "WITH __ref__a AS (SELECT 1 AS id), __expected__b AS (SELECT 1 AS id) SELECT 1", "fileLabel": "tests/unit/plain.sql", "mode": "model"}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__ref__stg_orders","SELECT E'O\\'Brien), (' AS customer_name"]],"macroMocks":[],"mockModels":["stg_orders"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[],"expectedModels":[],"assertions":[["__assert__named","SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"assertionNames":["named"]},{"kind":"model","mode":"model","authored":[["__ref__a","SELECT 1 AS id"]],"macroMocks":[],"mockModels":["a"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__b","SELECT 1 AS id"]],"expectedModels":["b"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro duplicate actual",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1), __macro_actual__ AS (SELECT 2)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' defines duplicate CTE '__macro_actual__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro duplicate expected",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_expected__ AS (SELECT 1 AS value), __macro_expected__ AS (SELECT 2 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' defines duplicate CTE '__macro_expected__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro model-test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __ref__orders AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'macro' but defines model-test CTE '__ref__orders'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro udf-test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'macro' but defines UDF-test CTE '__udf_actual__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro table_fn-test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_expected__ AS (SELECT 1 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'macro' but defines table_fn-test CTE '__table_fn_expected__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro reserved helper name",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __missing__ AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' uses reserved helper CTE name '__missing__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro missing expected",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'macro' must define exactly one __macro_actual__ CTE and exactly one __macro_expected__ CTE","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro helper calls macro",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH helper AS (SELECT @normalize_status('paid') AS status), __macro_actual__ AS (SELECT 1 AS status), __macro_expected__ AS (SELECT 1 AS status)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'macro' helper CTE 'helper' must not call macros; call macros only in __macro_actual__","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro expected calls macro",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS status), __macro_expected__ AS (SELECT @normalize_status('paid') AS status)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'macro' CTE __macro_expected__ must not call macros","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: macro expected unaliased projection names the expected cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS status), __macro_expected__ AS (SELECT 1 + 1)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must alias every non-trivial __macro_expected__ projection","help":"name the column with an alias, for example 1 + 1 AS <name>; only a bare or qualified column reference may go unaliased","token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn expected branch mismatch names the expected cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS value), __table_fn_expected__ AS (SELECT 1 AS value UNION ALL SELECT 2 AS other)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __table_fn_expected__ projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf duplicate actual",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1), __udf_actual__ AS (SELECT 2)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' defines duplicate CTE '__udf_actual__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf duplicate expected",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_expected__ AS (SELECT 1 AS value), __udf_expected__ AS (SELECT 2 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' defines duplicate CTE '__udf_expected__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf model-test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __expected__orders AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'udf' but defines model-test CTE '__expected__orders'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf macro-test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_expected__ AS (SELECT 1 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'udf' but defines macro-test CTE '__macro_expected__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf table_fn-test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'udf' but defines table_fn-test CTE '__table_fn_actual__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf reserved helper name",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __actual AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' uses reserved helper CTE name '__actual'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf missing actual",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_expected__ AS (SELECT 1 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'udf' must define exactly one __udf_actual__ CTE and exactly one __udf_expected__ CTE","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf helper calls macro",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH helper AS (SELECT @normalize_status('paid') AS status), __udf_actual__ AS (SELECT 1 AS formatted), __udf_expected__ AS (SELECT 1 AS formatted)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'udf' helper CTE 'helper' must not call macros","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: udf expected calls udf",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS formatted), __udf_expected__ AS (SELECT __udf(\"format_cents\")(1250) AS formatted)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'udf' CTE __udf_expected__ must not call udf; call reusable logic only in __udf_actual__","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn duplicate actual",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1), __table_fn_actual__ AS (SELECT 2)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' defines duplicate CTE '__table_fn_actual__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn duplicate expected",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_expected__ AS (SELECT 1 AS value), __table_fn_expected__ AS (SELECT 2 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' defines duplicate CTE '__table_fn_expected__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn model-test cte",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'table_fn' but defines model-test CTE '__source__raw_orders'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn macro cte uses generic direct-logic wording",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'table_fn' but defines another direct-logic CTE '__macro_actual__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn udf cte uses generic direct-logic wording",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_expected__ AS (SELECT 1 AS value)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' is mode 'table_fn' but defines another direct-logic CTE '__udf_expected__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn reserved helper name",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __unexpected__ AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' uses reserved helper CTE name '__unexpected__'","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "direct logic: table_fn missing both",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH helper AS (SELECT 1)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' mode 'table_fn' must define exactly one __table_fn_actual__ CTE and exactly one __table_fn_expected__ CTE","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: model: SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: model: SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: model: SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: model: SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: model: SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: model: SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: model: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"model","mode":"model","authored":[["__source__raw_orders","SELECT 1 AS order_id"]],"macroMocks":[],"mockModels":[],"mockSources":["raw_orders"],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__orders","SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id"]],"expectedModels":["orders"],"assertions":[],"assertionNames":[]}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: macro: SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT 1 AS order_id"],"expected":["__macro_expected__","SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: macro: SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT 1 AS order_id"],"expected":["__macro_expected__","SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: macro: SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT 1 AS order_id"],"expected":["__macro_expected__","SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: macro: SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT 1 AS order_id"],"expected":["__macro_expected__","SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: macro: SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT 1 AS order_id"],"expected":["__macro_expected__","SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: macro: SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT 1 AS order_id"],"expected":["__macro_expected__","SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: macro: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"macro","helpers":[],"actual":["__macro_actual__","SELECT 1 AS order_id"],"expected":["__macro_expected__","SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: udf: SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[],"actual":["__udf_actual__","SELECT 1 AS order_id"],"expected":["__udf_expected__","SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: udf: SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[],"actual":["__udf_actual__","SELECT 1 AS order_id"],"expected":["__udf_expected__","SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: udf: SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[],"actual":["__udf_actual__","SELECT 1 AS order_id"],"expected":["__udf_expected__","SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: udf: SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[],"actual":["__udf_actual__","SELECT 1 AS order_id"],"expected":["__udf_expected__","SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: udf: SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[],"actual":["__udf_actual__","SELECT 1 AS order_id"],"expected":["__udf_expected__","SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: udf: SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[],"actual":["__udf_actual__","SELECT 1 AS order_id"],"expected":["__udf_expected__","SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: udf: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"udf","helpers":[],"actual":["__udf_actual__","SELECT 1 AS order_id"],"expected":["__udf_expected__","SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: table_fn: SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT 1 AS order_id"],"expected":["__table_fn_expected__","SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: table_fn: SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT 1 AS order_id"],"expected":["__table_fn_expected__","SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: table_fn: SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT 1 AS order_id"],"expected":["__table_fn_expected__","SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: table_fn: SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT 1 AS order_id"],"expected":["__table_fn_expected__","SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: table_fn: SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT 1 AS order_id"],"expected":["__table_fn_expected__","SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: table_fn: SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT 1 AS order_id"],"expected":["__table_fn_expected__","SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation: table_fn: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"tests":[{"kind":"direct","mode":"table_fn","helpers":[],"actual":["__table_fn_actual__","SELECT 1 AS order_id"],"expected":["__table_fn_expected__","SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id"],"invalidCalls":false}]}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: model: SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __expected__orders projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: model: SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __expected__orders projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: model: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __expected__orders projection names and order in every set-operation branch; branch 3 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: model: SELECT 1 AS order_id EXCEPT VALUES (1)",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id EXCEPT VALUES (1))", "fileLabel": "tests/unit/orders.sql", "mode": "model", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must define each __expected__orders set-operation branch as a SELECT query","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: macro: SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __macro_expected__ projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: macro: SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __macro_expected__ projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: macro: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __macro_expected__ projection names and order in every set-operation branch; branch 3 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: macro: SELECT 1 AS order_id EXCEPT VALUES (1)",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __macro_actual__ AS (SELECT 1 AS order_id), __macro_expected__ AS (SELECT 1 AS order_id EXCEPT VALUES (1))", "fileLabel": "tests/unit/orders.sql", "mode": "macro", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must define each __macro_expected__ set-operation branch as a SELECT query","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: udf: SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __udf_expected__ projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: udf: SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __udf_expected__ projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: udf: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __udf_expected__ projection names and order in every set-operation branch; branch 3 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: udf: SELECT 1 AS order_id EXCEPT VALUES (1)",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __udf_actual__ AS (SELECT 1 AS order_id), __udf_expected__ AS (SELECT 1 AS order_id EXCEPT VALUES (1))", "fileLabel": "tests/unit/orders.sql", "mode": "udf", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must define each __udf_expected__ set-operation branch as a SELECT query","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: table_fn: SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __table_fn_expected__ projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: table_fn: SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __table_fn_expected__ projection names and order in every set-operation branch; branch 2 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: table_fn: SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id)", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must use the same __table_fn_expected__ projection names and order in every set-operation branch; branch 3 does not match branch 1","help":null,"token":null,"tokenOffset":null}}"####,
        },
        BatchClassificationTestCase {
            description: "set operation rejected: table_fn: SELECT 1 AS order_id EXCEPT VALUES (1)",
            request: r####"{"syntax": {"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}, "tests": [{"sql": "WITH __table_fn_actual__ AS (SELECT 1 AS order_id), __table_fn_expected__ AS (SELECT 1 AS order_id EXCEPT VALUES (1))", "fileLabel": "tests/unit/orders.sql", "mode": "table_fn", "raw": true}]}"####,
            expected_response: r####"{"error":{"index":0,"message":"SQL test 'tests/unit/orders.sql' must define each __table_fn_expected__ set-operation branch as a SELECT query","help":null,"token":null,"tokenOffset":null}}"####,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            batch_outcome(test_case.request),
            test_case.expected_response,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_macro_free_sql_tests_when_classifying_before_and_after_expansion_then_payloads_match() {
    let test_cases = [
        ExtractionParityTestCase {
            description: "model roles retain authored ordering and independent checks",
            sql: "WITH helper AS (SELECT 1 AS order_id), __source__raw_orders AS (SELECT order_id FROM helper), __macro__status AS (SELECT '''created'''), __expected__orders AS (SELECT order_id FROM helper), __assert__positive AS (SELECT order_id FROM helper WHERE order_id < 0) SELECT 1",
            mode: "model",
            expected_matches: true,
        },
        ExtractionParityTestCase {
            description: "macro direct logic retains helper actual and expected payloads",
            sql: "WITH input AS (SELECT 'created' AS status), __macro_actual__ AS (SELECT @normalize_status(status) AS status FROM input), __macro_expected__ AS (SELECT 'created' AS status) SELECT 1",
            mode: "macro",
            expected_matches: true,
        },
        ExtractionParityTestCase {
            description: "udf direct logic retains helper actual and expected payloads",
            sql: "WITH input AS (SELECT 1 AS value), __udf_actual__ AS (SELECT __udf(\"increment\")(value) AS value FROM input), __udf_expected__ AS (SELECT 2 AS value) SELECT 1",
            mode: "udf",
            expected_matches: true,
        },
        ExtractionParityTestCase {
            description: "table function direct logic retains actual and expected payloads",
            sql: "WITH __table_fn_actual__ AS (SELECT order_id FROM __table_fn(\"customer_orders\")(1)), __table_fn_expected__ AS (SELECT 1 AS order_id) SELECT 1",
            mode: "table_fn",
            expected_matches: true,
        },
        ExtractionParityTestCase {
            description: "expected projection before where without from is accepted",
            sql: "WITH __source__raw_orders AS (SELECT 1 AS id), __expected__orders AS (SELECT CAST(NULL AS INTEGER) AS id WHERE 1 = 0) SELECT 1",
            mode: "model",
            expected_matches: true,
        },
        ExtractionParityTestCase {
            description: "qualified expected projection uses the column name",
            sql: "WITH __source__raw_orders AS (SELECT 1 AS id), sample AS (SELECT 1 AS id), __expected__orders AS (SELECT sample.id FROM sample) SELECT 1",
            mode: "model",
            expected_matches: true,
        },
        ExtractionParityTestCase {
            description: "clause-like qualified column uses its explicit alias",
            sql: "WITH __source__raw_orders AS (SELECT 1 AS id), sample AS (SELECT 1 AS limit), __expected__orders AS (SELECT sample.limit AS id FROM sample) SELECT 1",
            mode: "model",
            expected_matches: true,
        },
    ];
    for test_case in test_cases {
        let raw = parity_payload(test_case.sql, test_case.mode, true);
        let expanded = parity_payload(test_case.sql, test_case.mode, false);

        assert_eq!(
            (raw.0 == expanded.0, raw.1),
            (test_case.expected_matches, false),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_scenarios_when_classifying_then_outcomes_are_exact() {
    let test_cases = [
        ScenarioClassificationTestCase {
            description: "roles: extracts dbt ref fixtures",
            sql: "WITH\n        __dbt_ref__orders AS (SELECT 1 AS order_id),\n        __dbt_ref__stripe__payments AS (SELECT 1 AS payment_id),\n        __expected__fact_orders AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__dbt_ref__orders","SELECT 1 AS order_id"],["__dbt_ref__stripe__payments","SELECT 1 AS payment_id"]],"expected":[["__expected__fact_orders","SELECT 1 AS order_id"]],"assertions":[],"sourceFixtures":[],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":["orders","stripe__payments"],"expectedModels":["fact_orders"],"assertionNames":[]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "roles: extracts fixtures when the trailing select is omitted",
            sql: "WITH\n        __ref__stg_orders AS (SELECT 1 AS order_id),\n        __expected__daily_revenue AS (SELECT 1 AS order_id)",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__ref__stg_orders","SELECT 1 AS order_id"]],"expected":[["__expected__daily_revenue","SELECT 1 AS order_id"]],"assertions":[],"sourceFixtures":[],"refFixtures":["stg_orders"],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":["daily_revenue"],"assertionNames":[]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "roles: extracts source ref seed fixtures expectations and assertions",
            sql: "WITH\n        helper_customers AS (SELECT 10 AS customer_id),\n        __source__raw__orders AS (SELECT 1 AS order_id, 10 AS customer_id),\n        __ref__stg_customers AS (SELECT customer_id FROM helper_customers),\n        __seed__waffle_types AS (SELECT 1 AS waffle_type_id),\n        __expected__daily_revenue AS (SELECT 1 AS order_id),\n        __assert__no_negative_revenue AS (\n          SELECT * FROM __ref(\"daily_revenue\") WHERE revenue < 0\n        )\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["helper_customers","SELECT 10 AS customer_id"],["__source__raw__orders","SELECT 1 AS order_id, 10 AS customer_id"],["__ref__stg_customers","SELECT customer_id FROM helper_customers"],["__seed__waffle_types","SELECT 1 AS waffle_type_id"]],"expected":[["__expected__daily_revenue","SELECT 1 AS order_id"]],"assertions":[["__assert__no_negative_revenue","SELECT * FROM __ref(\"daily_revenue\") WHERE revenue < 0"]],"sourceFixtures":["raw__orders"],"refFixtures":["stg_customers"],"seedFixtures":["waffle_types"],"dbtRefFixtures":[],"expectedModels":["daily_revenue"],"assertionNames":["no_negative_revenue"]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "roles: allows assertion only scenario target inference later",
            sql: "WITH\n        __source__raw__orders AS (SELECT 1 AS order_id),\n        __assert__has_no_null_orders AS (\n          SELECT * FROM __ref(\"fact_orders\") WHERE order_id IS NULL\n        )\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__source__raw__orders","SELECT 1 AS order_id"]],"expected":[],"assertions":[["__assert__has_no_null_orders","SELECT * FROM __ref(\"fact_orders\") WHERE order_id IS NULL"]],"sourceFixtures":["raw__orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":[],"assertionNames":["has_no_null_orders"]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "roles: allows expected only scenario with ref fixture",
            sql: "WITH\n        __ref__orders_base AS (SELECT 1 AS order_id),\n        __expected__fact_orders AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__ref__orders_base","SELECT 1 AS order_id"]],"expected":[["__expected__fact_orders","SELECT 1 AS order_id"]],"assertions":[],"sourceFixtures":[],"refFixtures":["orders_base"],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":["fact_orders"],"assertionNames":[]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "roles: allows expected only scenario with seed fixture",
            sql: "WITH\n        __seed__country_codes AS (SELECT 'US' AS country_code),\n        __expected__dim_countries AS (SELECT 'US' AS country_code)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__seed__country_codes","SELECT 'US' AS country_code"]],"expected":[["__expected__dim_countries","SELECT 'US' AS country_code"]],"assertions":[],"sourceFixtures":[],"refFixtures":[],"seedFixtures":["country_codes"],"dbtRefFixtures":[],"expectedModels":["dim_countries"],"assertionNames":[]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when ceremonial select is wrapped in a final result cte",
            sql: "WITH\n        __ref__orders_base AS (SELECT 1 AS order_id),\n        __expected__fact_orders AS (SELECT 1 AS order_id),\n        scenario_result AS (SELECT 1)\n        SELECT * FROM scenario_result",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when assertion depends directly on expected result",
            sql: "WITH\n        __source__raw__orders AS (SELECT 1 AS order_id),\n        __expected__orders AS (SELECT 1 AS order_id),\n        __assert__expected_is_nonempty AS (SELECT * FROM __expected__orders)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' check CTE '__assert__expected_is_nonempty' must not depend on '__expected__orders'; expected results and assertions must be independent"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when expected result depends indirectly on assertion",
            sql: "WITH\n        __source__raw__orders AS (SELECT 1 AS order_id),\n        __assert__positive_order_id AS (SELECT 1 AS order_id WHERE order_id < 1),\n        assertion_helper AS (SELECT * FROM __assert__positive_order_id),\n        __expected__orders AS (SELECT * FROM assertion_helper)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' check CTE '__expected__orders' must not depend on '__assert__positive_order_id' through 'assertion_helper'; expected results and assertions must be independent"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when a scenario cte name is quoted",
            sql: "WITH\n        \"__source__raw__orders\" AS (SELECT 1 AS order_id),\n        __expected__daily_revenue AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' expected a CTE name"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when a scenario cte uses a materialization hint",
            sql: "WITH\n        __source__raw__orders AS MATERIALIZED (SELECT 1 AS order_id),\n        __expected__daily_revenue AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' CTE '__source__raw__orders' must not use AS MATERIALIZED; materialization hints are not supported in SQL scenario CTEs"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when scenario has no fixture ctes",
            sql: "WITH __expected__fact_orders AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' must define at least one __source__*, __ref__*, __seed__*, or __dbt_ref__* fixture CTE"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when scenario has no expected or assertion ctes",
            sql: "WITH __source__raw__orders AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' must define at least one __expected__<model> or __assert__<assertion> CTE"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when scenario uses macro mock cte",
            sql: "WITH\n        __source__raw__orders AS (SELECT 1 AS order_id),\n        __macro__country AS (SELECT '''US'''),\n        __expected__fact_orders AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' does not support macro mock CTE '__macro__country'. Scenarios run real project macros; use SQL unit tests for macro mocks."}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when assertion cte suffix is missing",
            sql: "WITH\n        __source__raw__orders AS (SELECT 1 AS order_id),\n        __assert__ AS (SELECT * FROM __ref(\"fact_orders\"))\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' must use __assert__<assertion> to identify a target"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when duplicate cte names are present",
            sql: "WITH\n        __source__raw__orders AS (SELECT 1 AS order_id),\n        __source__raw__orders AS (SELECT 2 AS order_id),\n        __expected__fact_orders AS (SELECT 1 AS order_id)\n        SELECT 1",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' defines duplicate CTE '__source__raw__orders'"}"####,
        },
        ScenarioClassificationTestCase {
            description: "invalid: raises when fallback terminal read follows a set operation",
            sql: "WITH\n        \"__ref__orders_base\" AS (SELECT 1 AS order_id),\n        \"__expected__fact_orders\" AS (SELECT 1 AS order_id),\n        scenario_result AS (SELECT 1)\n        SELECT 2 UNION ALL SELECT * FROM scenario_result",
            file_label: "tests/scenarios/revenue__customer_refund.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/revenue__customer_refund.sql' expected a CTE name"}"####,
        },
        ScenarioClassificationTestCase {
            description: "malformed: scenario without a with clause uses scenario wording",
            sql: "SELECT * FROM orders",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/orders.sql' must declare fixture CTEs and at least one __expected__<model> or __assert__<assertion> CTE in a top-level WITH clause"}"####,
        },
        ScenarioClassificationTestCase {
            description: "malformed: unclosed comment before a fixture uses scenario wording",
            sql: "WITH /* unfinished",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario contains an unclosed block comment"}"####,
        },
        ScenarioClassificationTestCase {
            description: "malformed: unclosed trailing comment uses scenario wording",
            sql: "WITH __expected__orders AS (SELECT 1 AS order_id) SELECT 1; /* unfinished",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario contains an unclosed block comment"}"####,
        },
        ScenarioClassificationTestCase {
            description: "malformed: scenario with an invalid cte name uses scenario wording",
            sql: "WITH 1orders AS (SELECT 1) SELECT 1",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/orders.sql' expected a CTE name"}"####,
        },
        ScenarioClassificationTestCase {
            description: "malformed: scenario without a ceremonial select uses scenario wording",
            sql: "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id), result AS (SELECT 1) SELECT * FROM result",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/orders.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them"}"####,
        },
        ScenarioClassificationTestCase {
            description: "malformed: scenario fixture without a target uses scenario wording",
            sql: "WITH __source__ AS (SELECT 1 AS order_id), __expected__orders AS (SELECT 1 AS order_id) SELECT 1",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"error":"SQL scenario 'tests/scenarios/orders.sql' must use __source__<source> to identify a target"}"####,
        },
        ScenarioClassificationTestCase {
            description: "dialect: snowflake backslash-escaped quote before a marker",
            sql: "WITH\n__source__raw_orders AS (SELECT 'O\\'Brien), (' AS customer_name),\n__assert__named AS (\n  SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": ["'"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--", "//"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__source__raw_orders","SELECT 'O\\'Brien), (' AS customer_name"]],"expected":[],"assertions":[["__assert__named","SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"sourceFixtures":["raw_orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":[],"assertionNames":["named"]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "dialect: bigquery hash comment and triple quotes around markers",
            sql: "WITH\n__source__raw_orders AS (SELECT '''it's ), (''' AS note), # ), (\n__assert__named AS (\n  SELECT * FROM __ref(\"order_totals\") # __ref(\"ignored\")\n)\nSELECT 1",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": ["\"", "'", "`"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": true, "nestedBlockComments": false, "lineCommentPrefixes": ["#", "--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__source__raw_orders","SELECT '''it's ), (''' AS note"]],"expected":[],"assertions":[["__assert__named","SELECT * FROM __ref(\"order_totals\") # __ref(\"ignored\")"]],"sourceFixtures":["raw_orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":[],"assertionNames":["named"]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "dialect: databricks backslash-escaped quote before a marker",
            sql: "WITH\n__source__raw_orders AS (SELECT 'O\\'Brien), (' AS customer_name),\n__assert__named AS (\n  SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": ["\"", "'"], "escapeStringPrefix": false, "rawStringPrefix": true, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__source__raw_orders","SELECT 'O\\'Brien), (' AS customer_name"]],"expected":[],"assertions":[["__assert__named","SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"sourceFixtures":["raw_orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":[],"assertionNames":["named"]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "dialect: duckdb escape string and nested comment before a marker",
            sql: "WITH\n__source__raw_orders AS (SELECT E'O\\'Brien), (' AS customer_name),\n/* outer /* inner */ ), ( */\n__assert__named AS (\n  SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__source__raw_orders","SELECT E'O\\'Brien), (' AS customer_name"]],"expected":[],"assertions":[["__assert__named","SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"sourceFixtures":["raw_orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":[],"assertionNames":["named"]}}"####,
        },
        ScenarioClassificationTestCase {
            description: "dialect: postgres escape string before a marker",
            sql: "WITH\n__source__raw_orders AS (SELECT E'O\\'Brien), (' AS customer_name),\n__assert__named AS (\n  SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n)\nSELECT 1",
            file_label: "tests/scenarios/orders.sql",
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_outcome: r####"{"scenario":{"authored":[["__source__raw_orders","SELECT E'O\\'Brien), (' AS customer_name"]],"expected":[],"assertions":[["__assert__named","SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"]],"sourceFixtures":["raw_orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":[],"assertionNames":["named"]}}"####,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            scenario_outcome(test_case.sql, test_case.file_label, test_case.syntax),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_dialect_assertions_when_reading_targets_then_only_active_refs_count() {
    let test_cases = [
        AssertionTargetsTestCase {
            description: "scenario snowflake backslash-escaped quote before a marker",
            assertions: &["SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": ["'"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--", "//"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "scenario bigquery hash comment and triple quotes around markers",
            assertions: &["SELECT * FROM __ref(\"order_totals\") # __ref(\"ignored\")"],
            syntax: r####"{"backslashEscapeQuotes": ["\"", "'", "`"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": true, "nestedBlockComments": false, "lineCommentPrefixes": ["#", "--"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "scenario databricks backslash-escaped quote before a marker",
            assertions: &["SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": ["\"", "'"], "escapeStringPrefix": false, "rawStringPrefix": true, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "scenario duckdb escape string and nested comment before a marker",
            assertions: &["SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "scenario postgres escape string before a marker",
            assertions: &["SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "test snowflake backslash-escaped quote before a marker",
            assertions: &["SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": ["'"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--", "//"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "test bigquery hash comment and triple quotes around markers",
            assertions: &["SELECT * FROM __ref(\"order_totals\") # __ref(\"ignored\")"],
            syntax: r####"{"backslashEscapeQuotes": ["\"", "'", "`"], "escapeStringPrefix": false, "rawStringPrefix": false, "tripleQuotedStrings": true, "nestedBlockComments": false, "lineCommentPrefixes": ["#", "--"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "test databricks backslash-escaped quote before a marker",
            assertions: &["SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": ["\"", "'"], "escapeStringPrefix": false, "rawStringPrefix": true, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "test duckdb escape string and nested comment before a marker",
            assertions: &["SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_targets: &["order_totals"],
        },
        AssertionTargetsTestCase {
            description: "test postgres escape string before a marker",
            assertions: &["SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")"],
            syntax: r####"{"backslashEscapeQuotes": [], "escapeStringPrefix": true, "rawStringPrefix": false, "tripleQuotedStrings": false, "nestedBlockComments": true, "lineCommentPrefixes": ["--"]}"####,
            expected_targets: &["order_totals"],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            assertion_targets(test_case.assertions, test_case.syntax),
            test_case.expected_targets,
            "{}",
            test_case.description
        );
    }
}
