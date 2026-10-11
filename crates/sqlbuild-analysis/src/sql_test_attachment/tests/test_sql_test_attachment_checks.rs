//! The native SQL-test attachment checks: helper reads, authored offsets and stored scans.

use std::collections::HashSet;

use crate::assembly::analysis_session::main::sql_test_helper_reads::sql_test_helper_reads;
use crate::sql_test_attachment::main::authored_test_offset::authored_test_offset;
use crate::sql_test_attachment::main::sql_test_reads::sql_test_reads;
use crate::sql_test_attachment::main::stored_sql_tests::stored_sql_tests;
use crate::sql_test_attachment::main::test_without_target_model::test_without_target_model;
use crate::sql_test_attachment::main::unresolvable_test_references::unresolvable_test_references;
use crate::sql_test_attachment::models::{SqlTestHelperProblem, SqlTestReadFacts};
use crate::sql_test_attachment::tests::helpers::{
    generic_dash_syntax, model_test_ctes, problem_summary,
};
use crate::sql_test_attachment::tests::test_types::{
    AsciiMatcher, AttachmentCheckTestCase, AuthoredOffsetTestCase, HelperReadsTestCase,
    StoredScanTestCase,
};

#[test]
fn given_cte_bodies_when_reading_helper_keys_then_only_unqualified_unshadowed_reads_count() {
    let keys: Vec<String> = ["base", "helper", "mock_orders", "étapé"]
        .iter()
        .map(|key| (*key).to_owned())
        .collect();
    let test_cases = [
        HelperReadsTestCase {
            description: "a plain read",
            body: "SELECT * FROM base",
            expected_reads: Some(&["base"]),
        },
        HelperReadsTestCase {
            description: "case-insensitive reads in first-read order",
            body: "SELECT * FROM BASE JOIN helper h ON 1=1 JOIN base b2 ON 1=1",
            expected_reads: Some(&["base", "helper"]),
        },
        HelperReadsTestCase {
            description: "qualified names are not helper reads",
            body: "SELECT * FROM s.base JOIN db.s.helper ON 1=1",
            expected_reads: Some(&[]),
        },
        HelperReadsTestCase {
            description: "a nested CTE shadows its name",
            body: "WITH base AS (SELECT 1) SELECT * FROM base, helper",
            expected_reads: Some(&["helper"]),
        },
        HelperReadsTestCase {
            description: "a subquery CTE shadows only inside it",
            body: "SELECT * FROM (WITH Helper AS (SELECT 1) SELECT * FROM helper) x JOIN base ON 1=1",
            expected_reads: Some(&["base"]),
        },
        HelperReadsTestCase {
            description: "no table",
            body: "SELECT 1",
            expected_reads: Some(&[]),
        },
        HelperReadsTestCase {
            description: "an unrelated table",
            body: "SELECT * FROM unrelated",
            expected_reads: Some(&[]),
        },
        HelperReadsTestCase {
            description: "unparseable SQL",
            body: "SELECT * FROM base WHERE (",
            expected_reads: None,
        },
        HelperReadsTestCase {
            description: "a Unicode name folds",
            body: "SELECT * FROM ÉTAPÉ",
            expected_reads: Some(&["étapé"]),
        },
        HelperReadsTestCase {
            description: "a quoted name folds",
            body: "SELECT * FROM \"Base\"",
            expected_reads: Some(&["base"]),
        },
        HelperReadsTestCase {
            description: "set operations and subqueries",
            body: "SELECT * FROM mock_orders UNION ALL SELECT * FROM helper WHERE id IN (SELECT id FROM base)",
            expected_reads: Some(&["mock_orders", "helper", "base"]),
        },
        HelperReadsTestCase {
            description: "a column named like a helper",
            body: "SELECT base FROM other",
            expected_reads: Some(&[]),
        },
        HelperReadsTestCase {
            description: "several statements do not parse as one",
            body: "SELECT * FROM helper; SELECT * FROM base",
            expected_reads: None,
        },
        HelperReadsTestCase {
            description: "an EXISTS subquery",
            body: "SELECT * FROM t WHERE EXISTS (SELECT 1 FROM helper)",
            expected_reads: Some(&["helper"]),
        },
    ];
    for test_case in test_cases {
        let reads = sql_test_helper_reads(test_case.body, &keys).expect("the reads are computed");

        assert_eq!(
            reads,
            test_case.expected_reads.map(|reads| reads
                .iter()
                .map(|read| (*read).to_owned())
                .collect::<Vec<_>>()),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_discovered_block_when_mapping_body_offset_then_points_at_authored_text() {
    let test_cases = [
        AuthoredOffsetTestCase {
            description: "flush-left body after a comment that repeats the marker",
            contents: "TEST ();\n-- zz_mark is named here\nWITH\nzz_mark AS (SELECT 1 AS a)\n",
            authored: "-- zz_mark is named here\nWITH\nzz_mark AS (SELECT 1 AS a)",
            span: Some((9, 65)),
            body_offset: 30,
            marker: "zz_mark AS",
            expected_line_column: (4, 1),
        },
        AuthoredOffsetTestCase {
            description: "indented body with a tab before the marker",
            contents: "TEST ();\n    WITH\n    h AS (SELECT 1 AS a),\n    \tzz_mark AS (SELECT 1)\n",
            authored: "WITH\nh AS (SELECT 1 AS a),\n    zz_mark AS (SELECT 1)",
            span: Some((13, 70)),
            body_offset: 31,
            marker: "zz_mark",
            expected_line_column: (4, 6),
        },
        AuthoredOffsetTestCase {
            description: "tab inside a line before the marker",
            contents: "TEST ();\nWITH\nh AS (SELECT 1\t AS a, 'é' AS zz_mark)\n",
            authored: "WITH\nh AS (SELECT 1   AS a, 'é' AS zz_mark)",
            span: Some((9, 51)),
            body_offset: 35,
            marker: "zz_mark",
            expected_line_column: (3, 30),
        },
        AuthoredOffsetTestCase {
            description: "second block with blank lines after its header",
            contents: "TEST (name \"one\");\nWITH a AS (SELECT 1)\n;\nTEST (name \"two\");\n\n\n  WITH\n  b AS (SELECT zz_mark)\n",
            authored: "WITH\nb AS (SELECT zz_mark)",
            span: Some((65, 93)),
            body_offset: 18,
            marker: "zz_mark",
            expected_line_column: (8, 16),
        },
        AuthoredOffsetTestCase {
            description: "first body line indented on the header line",
            contents: "TEST ();   WITH zz_mark AS (SELECT 1)\n  , b AS (SELECT 2)\n",
            authored: "WITH zz_mark AS (SELECT 1)\n, b AS (SELECT 2)",
            span: Some((11, 57)),
            body_offset: 5,
            marker: "zz_mark",
            expected_line_column: (1, 17),
        },
    ];
    for test_case in test_cases {
        let offset: usize = authored_test_offset(
            test_case.contents,
            test_case.authored,
            test_case.span,
            test_case.body_offset,
        )
        .expect("the offset is exact");
        let before: Vec<char> = test_case.contents.chars().take(offset).collect();
        let marker: String = test_case
            .contents
            .chars()
            .skip(offset)
            .take(test_case.marker.chars().count())
            .collect();
        let line: usize = before
            .iter()
            .filter(|character| **character == '\n')
            .count()
            + 1;
        let column: usize = offset
            - before
                .iter()
                .rposition(|character| *character == '\n')
                .map_or(0, |index| index + 1)
            + 1;

        assert_eq!(
            (marker.as_str(), (line, column)),
            (test_case.marker, test_case.expected_line_column),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_stored_scan_bytes_when_decoding_then_only_exact_shapes_are_reused() {
    let model: &str = r#"{"kind":"model","mode":"model","authored":[["__ref__a","SELECT 1"]],"macroMocks":[],"mockModels":["a"],"mockSources":[],"mockSeeds":[],"mockDbtRefs":[],"mockTableFunctions":[],"expected":[["__expected__b","SELECT 1"]],"expectedModels":["b"],"assertions":[],"assertionNames":[]}"#;
    let test_cases = [
        StoredScanTestCase {
            description: "an exact model result is reused",
            value: format!("[{model}]"),
            modes: &["model"],
            expected_reused: true,
        },
        StoredScanTestCase {
            description: "undecodable bytes are rescanned",
            value: "{]".to_owned(),
            modes: &["model"],
            expected_reused: false,
        },
        StoredScanTestCase {
            description: "a misshapen entry is rescanned",
            value: r#"[{"mode": "model"}]"#.to_owned(),
            modes: &["model"],
            expected_reused: false,
        },
        StoredScanTestCase {
            description: "a different test count is rescanned",
            value: format!("[{model}]"),
            modes: &["model", "model"],
            expected_reused: false,
        },
        StoredScanTestCase {
            description: "a changed mode is rescanned",
            value: format!("[{model}]"),
            modes: &["macro"],
            expected_reused: false,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            stored_sql_tests(test_case.value.as_bytes(), test_case.modes).is_some(),
            test_case.expected_reused,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_model_tests_when_checking_helpers_then_reads_and_problems_are_reported() {
    let test_cases = [
        AttachmentCheckTestCase {
            description: "an expected CTE reading a helper that reads an unmocked model",
            authored: &[
                ("__source__raw", "SELECT 1 AS id"),
                ("helper", "SELECT * FROM __ref(\"orders\")"),
            ],
            expected: &[("__expected__orders", "SELECT * FROM helper")],
            assertions: &[],
            mocks: (&[], &["raw"]),
            expected_reads: (&["helper"], &["orders"]),
            expected_problems: &[],
            expected_without_target: "SQL test 'orders' reads no model, so the test has no model to run against @ __expected__orders",
        },
        AttachmentCheckTestCase {
            description: "an assertion calling an unmocked source",
            authored: &[("__ref__stg", "SELECT 1 AS id")],
            expected: &[],
            assertions: &[("__assert__ok", "SELECT * FROM __source(\"raw\")")],
            mocks: (&["stg"], &[]),
            expected_reads: (&[], &[]),
            expected_problems: &[
                "SQL test assertion CTE '__assert__ok' calls __source(\"raw\"), which the test does not mock, so the test query cannot resolve it @ __assert__ok: __source(\"raw\")",
            ],
            expected_without_target: "SQL test 'orders' reads no model, so the test has no model to run against @ __assert__ok",
        },
        AttachmentCheckTestCase {
            description: "an expected CTE reading an unknown model",
            authored: &[("__source__raw", "SELECT 1 AS id")],
            expected: &[("__expected__orders", "SELECT * FROM __ref(\"missing\")")],
            assertions: &[],
            mocks: (&[], &["raw"]),
            expected_reads: (&[], &["missing"]),
            expected_problems: &[
                "SQL test expected CTE '__expected__orders' references unknown model 'missing' @ __expected__orders: __ref(\"missing\")",
            ],
            expected_without_target: "SQL test 'orders' reads no model, so the test has no model to run against @ __expected__orders",
        },
        AttachmentCheckTestCase {
            description: "helpers reading each other",
            authored: &[
                ("__source__raw", "SELECT 1 AS id"),
                ("first", "SELECT * FROM second"),
                ("second", "SELECT * FROM first"),
            ],
            expected: &[("__expected__orders", "SELECT * FROM first")],
            assertions: &[],
            mocks: (&[], &["raw"]),
            expected_reads: (&["first", "second"], &[]),
            expected_problems: &[
                "SQL test CTE 'first' reads itself through 'first' -> 'second' -> 'first', so the test query cannot define its CTEs in dependency order @ first",
            ],
            expected_without_target: "SQL test 'orders' reads no model, so the test has no model to run against @ __expected__orders",
        },
        AttachmentCheckTestCase {
            description: "an assertion reading only the mock of the model it tests",
            authored: &[("__ref__orders", "SELECT 1 AS id")],
            expected: &[],
            assertions: &[("__assert__ok", "SELECT * FROM __ref__orders")],
            mocks: (&["orders"], &[]),
            expected_reads: (&[], &[]),
            expected_problems: &[],
            expected_without_target: "SQL test 'orders' mocks the model it tests (__ref__orders), so the test has no model to run against @ __assert__ok: __ref__orders",
        },
    ];
    let syntax = generic_dash_syntax();
    let known: HashSet<String> = ["orders".to_owned()].into_iter().collect();
    for test_case in test_cases {
        let (authored, expected, assertions, mock_models, mock_sources) = (
            crate::sql_test_attachment::tests::helpers::cte_texts(test_case.authored),
            crate::sql_test_attachment::tests::helpers::cte_texts(test_case.expected),
            crate::sql_test_attachment::tests::helpers::cte_texts(test_case.assertions),
            crate::sql_test_attachment::tests::helpers::owned(test_case.mocks.0),
            crate::sql_test_attachment::tests::helpers::owned(test_case.mocks.1),
        );
        let ctes = model_test_ctes(
            (&authored, &expected, &assertions),
            (&mock_models, &mock_sources),
        );

        let reads: SqlTestReadFacts = sql_test_reads(&ctes, &syntax, &AsciiMatcher).expect("reads");
        let problems: Vec<SqlTestHelperProblem> =
            unresolvable_test_references(&ctes, &known, &syntax, &AsciiMatcher).expect("problems");
        let without: SqlTestHelperProblem =
            test_without_target_model(&ctes, "orders", &syntax, &AsciiMatcher).expect("problem");

        assert_eq!(
            (
                (reads.read_helper_names, reads.reference_target_model_names),
                problems.iter().map(problem_summary).collect::<Vec<_>>(),
                problem_summary(&without),
            ),
            (
                (
                    crate::sql_test_attachment::tests::helpers::owned(test_case.expected_reads.0),
                    crate::sql_test_attachment::tests::helpers::owned(test_case.expected_reads.1),
                ),
                crate::sql_test_attachment::tests::helpers::owned(test_case.expected_problems),
                test_case.expected_without_target.to_owned(),
            ),
            "{}",
            test_case.description
        );
    }
}
