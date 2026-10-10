use crate::semantic_checks::_helpers::sql_text::parsed_sql::projection_spans;
use crate::semantic_checks::models::SemanticFailure;
use crate::semantic_checks::tests::helpers::{names, pairs, parsed_facts};
use crate::semantic_checks::tests::test_types::{ParsedFactsTestCase, ProjectionSpanTestCase};

#[test]
fn given_select_lists_when_finding_projection_spans_then_matches_python_tokens() {
    let test_cases = [
        ProjectionSpanTestCase {
            description: "aliases and a function call up to FROM",
            sql: "SELECT a, b AS c, f(x, y) FROM t",
            dialect: Some("duckdb"),
            expected_spans: Ok(&[(6, 8), (9, 16), (17, 26)]),
        },
        ProjectionSpanTestCase {
            description: "a nested select list ends at WHERE",
            sql: "SELECT a, (SELECT 1, 2) AS s\nWHERE 1 = 1",
            dialect: Some("duckdb"),
            expected_spans: Ok(&[(6, 8), (9, 29)]),
        },
        ProjectionSpanTestCase {
            description: "a select list running to the end",
            sql: "SELECT a, b",
            dialect: Some("duckdb"),
            expected_spans: Ok(&[(6, 8), (9, 11)]),
        },
        ProjectionSpanTestCase {
            description: "a CTE before the top-level select",
            sql: "WITH c AS (SELECT 1 AS x) SELECT x, y FROM c",
            dialect: Some("duckdb"),
            expected_spans: Ok(&[(32, 34), (35, 38)]),
        },
        ProjectionSpanTestCase {
            description: "code-point offsets after a non-ASCII literal",
            sql: "SELECT '\u{e9}', b FROM t",
            dialect: Some("duckdb"),
            expected_spans: Ok(&[(6, 10), (11, 14)]),
        },
        ProjectionSpanTestCase {
            description: "no dialect, which the wheel's tokenizer rejects",
            sql: "SELECT a",
            dialect: None,
            expected_spans: Err(SemanticFailure::NoDialect),
        },
        ProjectionSpanTestCase {
            description: "a dialect the all-dialects parser build added, as the wheel tokenizes it",
            sql: "SELECT a",
            dialect: Some("mysql"),
            expected_spans: Ok(&[(6, 8)]),
        },
        ProjectionSpanTestCase {
            description: "a dialect Polyglot does not know",
            sql: "SELECT a",
            dialect: Some("nonsense"),
            expected_spans: Err(SemanticFailure::UnknownDialect("nonsense".to_owned())),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            projection_spans(test_case.sql, test_case.dialect),
            test_case.expected_spans.map(<[(usize, usize)]>::to_vec),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_model_sql_when_parsing_then_finds_python_aliases_and_unaliased_outputs() {
    let test_cases = [
        ParsedFactsTestCase {
            description: "aliases, a shared alias name and an aliased projection",
            sql: "SELECT o.order_id, amount, c.name AS customer FROM __ref(\"orders\") AS o \
                  JOIN __ref(\"customers\") c ON TRUE JOIN __ref(\"orders\") AS c2 ON TRUE",
            expected_aliases: &[
                ("c", "customers"),
                ("c2", "orders"),
                ("customers", "customers"),
                ("o", "orders"),
                ("orders", "orders"),
            ],
            expected_unaliased: &["amount", "order_id"],
        },
        ParsedFactsTestCase {
            description: "a set operation has no top-level select list",
            sql: "SELECT a FROM __source(\"raw_orders\") UNION ALL SELECT b FROM t",
            expected_aliases: &[("raw_orders", "raw_orders"), ("t", "t")],
            expected_unaliased: &[],
        },
        ParsedFactsTestCase {
            description: "SQL the wheel cannot parse",
            sql: "SELECT FROM (",
            expected_aliases: &[],
            expected_unaliased: &[],
        },
    ];
    for test_case in test_cases {
        let (aliases, unaliased) = parsed_facts(test_case.sql);
        assert_eq!(
            aliases,
            pairs(test_case.expected_aliases),
            "{}",
            test_case.description
        );
        assert_eq!(
            unaliased,
            names(test_case.expected_unaliased),
            "{}",
            test_case.description
        );
    }
}
