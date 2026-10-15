use crate::planner_fixtures::main::{
    collection_mismatch::collection_mismatch, fixture_line::fixture_line,
};
use crate::planner_fixtures::tests::test_types::{CollectionMismatchTestCase, FixtureLineTestCase};

#[test]
fn given_fixture_cte_when_locating_then_reports_python_compatible_line() {
    let test_cases = [
        FixtureLineTestCase {
            description: "definition line",
            contents: "TEST();\n\nWITH\n__source__orders AS (SELECT 1)\n",
            cte_name: "__source__orders",
            expected_line: 4,
        },
        FixtureLineTestCase {
            description: "leading blank line starts the match",
            contents: "TEST();\nWITH\n\n__source__orders AS (SELECT 1)\n",
            cte_name: "__source__orders",
            expected_line: 3,
        },
        FixtureLineTestCase {
            description: "case-insensitive keyword across lines",
            contents: "WITH\n__expected__orders\n  as\n  (SELECT 1)\n",
            cte_name: "__expected__orders",
            expected_line: 2,
        },
        FixtureLineTestCase {
            description: "information separator counts as whitespace",
            contents: "WITH\n\u{1f}__ref__orders\u{1c}AS(SELECT 1)\n",
            cte_name: "__ref__orders",
            expected_line: 2,
        },
        FixtureLineTestCase {
            description: "missing definition falls back to line one",
            contents: "WITH /* x */ __seed__codes AS (SELECT 1)\n",
            cte_name: "__seed__codes",
            expected_line: 1,
        },
        FixtureLineTestCase {
            description: "name is matched literally",
            contents: "WITH\n__ref__aXb AS (SELECT 1)\n__ref__a.b AS (SELECT 1)\n",
            cte_name: "__ref__a.b",
            expected_line: 3,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            fixture_line(test_case.contents, test_case.cte_name).ok(),
            Some(test_case.expected_line),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_fixture_types_when_comparing_then_flags_collection_scalar_conflicts() {
    let test_cases = [
        CollectionMismatchTestCase {
            description: "array against scalar",
            expected_type: Some("ARRAY"),
            inferred_type: Some("VARCHAR"),
            expected_mismatch: true,
        },
        CollectionMismatchTestCase {
            description: "parameterized collections agree",
            expected_type: Some("struct(a INTEGER)"),
            inferred_type: Some(" MAP (VARCHAR, INTEGER)"),
            expected_mismatch: false,
        },
        CollectionMismatchTestCase {
            description: "scalars agree",
            expected_type: Some("INTEGER"),
            inferred_type: Some("NUMBER(38, 0)"),
            expected_mismatch: false,
        },
        CollectionMismatchTestCase {
            description: "unknown type never conflicts",
            expected_type: None,
            inferred_type: Some("ARRAY"),
            expected_mismatch: false,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            collection_mismatch(test_case.expected_type, test_case.inferred_type),
            test_case.expected_mismatch,
            "{}",
            test_case.description
        );
    }
}
