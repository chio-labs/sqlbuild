use crate::header_metadata::tests::helpers::{map, summary};
use crate::header_metadata::tests::test_types::HeaderMetadataTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_header_metadata_when_parsing_then_python_parses_and_errors_result() {
    let column = |metadata: &[(&'static str, Value)]| map(&[("order_id", map(metadata))]);
    let test_cases = [
        HeaderMetadataTestCase {
            description: "absent columns and audits declare nothing",
            columns: Value::Null,
            audits: Value::Null,
            expected_summary: Ok(&[]),
        },
        HeaderMetadataTestCase {
            description: "typed columns keep authored order, nullable and column audits",
            columns: map(&[
                (
                    "order_id",
                    map(&[
                        ("type", Value::Str("INTEGER")),
                        ("nullable", Value::Bool(false)),
                        (
                            "audits",
                            Value::List(vec![
                                Value::Str("not_null"),
                                map(&[("unique", Value::Null)]),
                            ]),
                        ),
                    ]),
                ),
                (
                    "Amount",
                    map(&[("description", Value::Str("Order amount"))]),
                ),
            ]),
            audits: Value::List(vec![map(&[(
                "row_count",
                map(&[
                    ("minimum", Value::Int(1)),
                    ("severity", Value::Str("warn")),
                    ("minimum_samples", Value::Int(0)),
                ]),
            )])]),
            expected_summary: Ok(&[
                "order_id INTEGER Bool(false) not_null:,unique:",
                "Amount - - ",
                "row_count:minimum@warn",
            ]),
        },
        HeaderMetadataTestCase {
            description: "an empty column mapping declares nothing",
            columns: Value::Map(Vec::new()),
            audits: Value::List(Vec::new()),
            expected_summary: Ok(&[]),
        },
        HeaderMetadataTestCase {
            description: "case-insensitive duplicate columns fail",
            columns: map(&[("id", map(&[])), ("ID", map(&[]))]),
            audits: Value::Null,
            expected_summary: Err(
                "/project/models/orders.sql model has duplicate column 'ID' (column names are case-insensitive)",
            ),
        },
        HeaderMetadataTestCase {
            description: "unknown column keys fail",
            columns: column(&[("format", Value::Str("x"))]),
            audits: Value::Null,
            expected_summary: Err(
                "/project/models/orders.sql model column 'order_id' has unknown metadata keys: format",
            ),
        },
        HeaderMetadataTestCase {
            description: "nullable true with not_null fails",
            columns: column(&[
                ("nullable", Value::Bool(true)),
                ("audits", Value::List(vec![Value::Str("not_null")])),
            ]),
            audits: Value::Null,
            expected_summary: Err(
                "/project/models/orders.sql column 'order_id' cannot set nullable = true and audit not_null",
            ),
        },
        HeaderMetadataTestCase {
            description: "blank or non-string text fails",
            columns: column(&[("type", Value::Str("  "))]),
            audits: Value::Null,
            expected_summary: Err(
                "/project/models/orders.sql model column 'order_id' 'type' must be a non-empty string",
            ),
        },
        HeaderMetadataTestCase {
            description: "non-ASCII column names compare case-insensitively",
            columns: map(&[("caf\u{e9}", map(&[])), ("CAF\u{c9}", map(&[]))]),
            audits: Value::Null,
            expected_summary: Err(
                "/project/models/orders.sql model has duplicate column 'CAF\u{c9}' (column names are case-insensitive)",
            ),
        },
        HeaderMetadataTestCase {
            description: "an audit name that is not snake_case fails",
            columns: Value::Null,
            audits: Value::List(vec![Value::Str("NotNull")]),
            expected_summary: Err(
                "Invalid model audit definition identity 'NotNull' in /project/models/orders.sql; use snake_case 'not_null'",
            ),
        },
        HeaderMetadataTestCase {
            description: "unknown severities, thresholds and negative counts fail",
            columns: Value::Null,
            audits: Value::List(vec![
                map(&[("a", map(&[("severity", Value::Str("fatal"))]))]),
                map(&[("b", map(&[("thresholds", map(&[]))]))]),
            ]),
            expected_summary: Err(
                "/project/models/orders.sql model audit 'a' 'severity' must be one of: warn, error",
            ),
        },
        HeaderMetadataTestCase {
            description: "empty thresholds need one bound",
            columns: Value::Null,
            audits: Value::List(vec![map(&[("b", map(&[("thresholds", map(&[]))]))])]),
            expected_summary: Err(
                "/project/models/orders.sql model audit 'b' invalid thresholds: at least one measurement threshold is required",
            ),
        },
        HeaderMetadataTestCase {
            description: "below error limits must sit under the warn limit",
            columns: Value::Null,
            audits: Value::List(vec![map(&[(
                "b",
                map(&[(
                    "thresholds",
                    map(&[
                        ("warn", map(&[("below", Value::Int(5))])),
                        ("error", map(&[("below", Value::Int(5))])),
                    ]),
                )]),
            )])]),
            expected_summary: Err(
                "/project/models/orders.sql model audit 'b' invalid thresholds: below error limit must be less than warn limit",
            ),
        },
        HeaderMetadataTestCase {
            description: "outside thresholds read their limits as floats",
            columns: Value::Null,
            audits: Value::List(vec![map(&[(
                "b",
                map(&[(
                    "thresholds",
                    map(&[
                        (
                            "warn",
                            map(&[("outside", Value::Tuple(vec![Value::Float, Value::Int(1)]))]),
                        ),
                        (
                            "error",
                            map(&[("outside", Value::Tuple(vec![Value::Int(0), Value::Int(2)]))]),
                        ),
                    ]),
                )]),
            )])]),
            expected_summary: Ok(&[
                "b: warn=Some(Outside(0.5, 1.0)) error=Some(Outside(0.0, 2.0))",
            ]),
        },
        HeaderMetadataTestCase {
            description: "outside bounds need a tuple of two numbers",
            columns: Value::Null,
            audits: Value::List(vec![map(&[(
                "b",
                map(&[(
                    "thresholds",
                    map(&[(
                        "warn",
                        map(&[("outside", Value::List(vec![Value::Int(1), Value::Int(2)]))]),
                    )]),
                )]),
            )])]),
            expected_summary: Err(
                "/project/models/orders.sql model audit 'b' invalid thresholds: outside threshold requires two numeric values",
            ),
        },
        HeaderMetadataTestCase {
            description: "ASCII control characters are text to Python's strip",
            columns: column(&[("description", Value::Str(" \u{1}"))]),
            audits: Value::Null,
            expected_summary: Ok(&["order_id - - "]),
        },
        HeaderMetadataTestCase {
            description: "a negative evidence limit fails",
            columns: Value::Null,
            audits: Value::List(vec![map(&[(
                "a",
                map(&[("evidence_limit", Value::Int(-1))]),
            )])]),
            expected_summary: Err(
                "/project/models/orders.sql model audit 'a' 'evidence_limit' must be a non-negative integer",
            ),
        },
        HeaderMetadataTestCase {
            description: "a boolean count fails",
            columns: Value::Null,
            audits: Value::List(vec![map(&[(
                "a",
                map(&[("minimum_samples", Value::Bool(true))]),
            )])]),
            expected_summary: Err(
                "/project/models/orders.sql model audit 'a' 'minimum_samples' must be a non-negative integer",
            ),
        },
        HeaderMetadataTestCase {
            description: "an audit list that is not a list fails",
            columns: Value::Null,
            audits: Value::Float,
            expected_summary: Err("/project/models/orders.sql model audits must be a list"),
        },
        HeaderMetadataTestCase {
            description: "a multi-key audit mapping fails",
            columns: Value::Null,
            audits: Value::List(vec![map(&[("a", Value::Null), ("b", Value::Null)])]),
            expected_summary: Err(
                "/project/models/orders.sql model audits must be strings or single-key mappings",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            summary(&test_case.columns, &test_case.audits),
            test_case
                .expected_summary
                .map(|lines| lines
                    .iter()
                    .map(|line| (*line).to_owned())
                    .collect::<Vec<_>>())
                .map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
