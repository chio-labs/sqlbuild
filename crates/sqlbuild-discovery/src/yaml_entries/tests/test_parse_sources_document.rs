use crate::yaml_entries::_helpers::freshness::freshness_minutes;
use crate::yaml_entries::tests::helpers::{dlt_group, map, sources, sources_outcome, text};
use crate::yaml_entries::tests::test_types::{
    FreshnessDurationTestCase, Node, SourcesDocumentTestCase, lines, parse_error,
};

#[test]
fn given_sources_documents_when_parsing_then_matches_python_sources_and_errors() {
    let test_cases = [
        SourcesDocumentTestCase {
            description: "a dlt resource becomes a managed source named after it",
            document: dlt_group(vec![
                ("type", text("sql_database")),
                (
                    "config",
                    map(vec![("credentials", text("duckdb:///shop.db"))]),
                ),
                ("schema", text("raw")),
                (
                    "resources",
                    Node::List(vec![map(vec![
                        ("name", text("orders")),
                        ("table", text("orders_v1")),
                    ])]),
                ),
            ]),
            expected_sources: lines(&["orders loader=orders managed=true schema=raw table=orders"]),
        },
        SourcesDocumentTestCase {
            description: "merge without a unique key",
            document: sources(vec![
                ("name", text("orders")),
                ("managed", Node::Bool(true)),
                ("write_strategy", text("merge")),
            ]),
            expected_sources: parse_error(
                "/project/sources/shop.yml source 'orders' write_strategy merge requires unique_key",
            ),
        },
        SourcesDocumentTestCase {
            description: "a write strategy on an unmanaged source",
            document: sources(vec![
                ("name", text("orders")),
                ("write_strategy", text("append")),
            ]),
            expected_sources: parse_error(
                "/project/sources/shop.yml source 'orders' defines write_strategy but is not managed",
            ),
        },
        SourcesDocumentTestCase {
            description: "the removed loader key",
            document: sources(vec![
                ("name", text("orders")),
                ("loader", text("load_orders")),
            ]),
            expected_sources: parse_error(
                "/project/sources/shop.yml source 'loader' is not supported; use managed: true \
                 and name the terminal loader after the source",
            ),
        },
        SourcesDocumentTestCase {
            description: "freshness type without column or query",
            document: sources(vec![
                ("name", text("orders")),
                ("freshness", map(vec![("type", text("timestamp"))])),
            ]),
            expected_sources: parse_error(
                "/project/sources/shop.yml source freshness type and filter require column or query",
            ),
        },
        SourcesDocumentTestCase {
            description: "a dlt resource with write_strategy",
            document: dlt_group(vec![
                ("type", text("filesystem")),
                ("config", map(vec![("bucket_url", text("s3://orders"))])),
                (
                    "resources",
                    Node::List(vec![map(vec![
                        ("name", text("orders")),
                        ("write_strategy", text("append")),
                    ])]),
                ),
            ]),
            expected_sources: parse_error(
                "/project/sources/shop.yml dlt resource 'orders' must use dlt write_disposition, \
                 not write_strategy",
            ),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            sources_outcome(&test_case.document),
            test_case.expected_sources,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_freshness_durations_when_measuring_then_matches_python_duration_rules() {
    let test_cases = [
        FreshnessDurationTestCase {
            description: "minutes",
            text: "15m",
            expected_minutes: Some(15),
        },
        FreshnessDurationTestCase {
            description: "hours",
            text: "2h",
            expected_minutes: Some(120),
        },
        FreshnessDurationTestCase {
            description: "days",
            text: "1d",
            expected_minutes: Some(1_440),
        },
        FreshnessDurationTestCase {
            description: "two units",
            text: "1d2h",
            expected_minutes: None,
        },
        FreshnessDurationTestCase {
            description: "seconds",
            text: "30s",
            expected_minutes: None,
        },
        FreshnessDurationTestCase {
            description: "zero",
            text: "0m",
            expected_minutes: None,
        },
        FreshnessDurationTestCase {
            description: "non-ASCII decimal digits",
            text: "\u{0661}\u{0665}m",
            expected_minutes: Some(15),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            freshness_minutes(test_case.text),
            test_case.expected_minutes,
            "{}",
            test_case.description
        );
    }
}
