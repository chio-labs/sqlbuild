use crate::header_metadata::models::HeaderMetadataDeferral;
use crate::header_metadata::tests::helpers::{map, summary};
use crate::header_metadata::tests::test_types::HeaderMetadataTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_header_metadata_when_parsing_then_happy_paths_parse_and_python_errors_defer() {
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
            description: "case-insensitive duplicate columns defer",
            columns: map(&[("id", map(&[])), ("ID", map(&[]))]),
            audits: Value::Null,
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "unknown column keys defer",
            columns: column(&[("format", Value::Str("x"))]),
            audits: Value::Null,
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "nullable true with not_null defers",
            columns: column(&[
                ("nullable", Value::Bool(true)),
                ("audits", Value::List(vec![Value::Str("not_null")])),
            ]),
            audits: Value::Null,
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "blank or non-string text defers",
            columns: column(&[("type", Value::Str("  "))]),
            audits: Value::Null,
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "non-ASCII column names defer to Python's lower()",
            columns: map(&[("caf\u{e9}", map(&[]))]),
            audits: Value::Null,
            expected_summary: Err(HeaderMetadataDeferral::Unsupported),
        },
        HeaderMetadataTestCase {
            description: "an audit name that is not snake_case defers",
            columns: Value::Null,
            audits: Value::List(vec![Value::Str("NotNull")]),
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "unknown severities, thresholds and negative counts defer",
            columns: Value::Null,
            audits: Value::List(vec![
                map(&[("a", map(&[("severity", Value::Str("fatal"))]))]),
                map(&[("b", map(&[("thresholds", map(&[]))]))]),
            ]),
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "thresholds are left to Python's parser",
            columns: Value::Null,
            audits: Value::List(vec![map(&[("b", map(&[("thresholds", map(&[]))]))])]),
            expected_summary: Err(HeaderMetadataDeferral::Unsupported),
        },
        HeaderMetadataTestCase {
            description: "ASCII control characters are text to Python's strip",
            columns: column(&[("description", Value::Str(" \u{1}"))]),
            audits: Value::Null,
            expected_summary: Ok(&["order_id - - "]),
        },
        HeaderMetadataTestCase {
            description: "a negative evidence limit defers",
            columns: Value::Null,
            audits: Value::List(vec![map(&[(
                "a",
                map(&[("evidence_limit", Value::Int(-1))]),
            )])]),
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "a boolean count defers",
            columns: Value::Null,
            audits: Value::List(vec![map(&[(
                "a",
                map(&[("minimum_samples", Value::Bool(true))]),
            )])]),
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "an audit list that is not a list defers",
            columns: Value::Null,
            audits: Value::Float,
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
        HeaderMetadataTestCase {
            description: "a multi-key audit mapping defers",
            columns: Value::Null,
            audits: Value::List(vec![map(&[("a", Value::Null), ("b", Value::Null)])]),
            expected_summary: Err(HeaderMetadataDeferral::Invalid),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            summary(&test_case.columns, &test_case.audits),
            test_case.expected_summary.map(|lines| lines
                .iter()
                .map(|line| (*line).to_owned())
                .collect::<Vec<_>>()),
            "{}",
            test_case.description
        );
    }
}
