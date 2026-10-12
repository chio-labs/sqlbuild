use crate::yaml_entries::_helpers::freshness::freshness_minutes;
use crate::yaml_entries::main::parse_sources_document::parse_sources_document;
use crate::yaml_entries::tests::test_types::{Node, map, text};

const PATH: &str = "/project/sources/shop.yml";

fn sources(entry: Vec<(&str, Node)>) -> Node {
    map(vec![("sources", Node::List(vec![map(entry)]))])
}

struct SourceErrorTestCase {
    description: &'static str,
    document: Node,
    expected_message: &'static str,
}

#[test]
fn given_invalid_sources_when_parsing_then_reports_python_messages() {
    let test_cases = [
        SourceErrorTestCase {
            description: "merge without a unique key",
            document: sources(vec![
                ("name", text("orders")),
                ("managed", Node::Bool(true)),
                ("write_strategy", text("merge")),
            ]),
            expected_message: "/project/sources/shop.yml source 'orders' write_strategy merge requires unique_key",
        },
        SourceErrorTestCase {
            description: "a write strategy on an unmanaged source",
            document: sources(vec![
                ("name", text("orders")),
                ("write_strategy", text("append")),
            ]),
            expected_message: "/project/sources/shop.yml source 'orders' defines write_strategy but is not managed",
        },
        SourceErrorTestCase {
            description: "the removed loader key",
            document: sources(vec![
                ("name", text("orders")),
                ("loader", text("load_orders")),
            ]),
            expected_message: "/project/sources/shop.yml source 'loader' is not supported; use managed: true and name the terminal loader after the source",
        },
        SourceErrorTestCase {
            description: "freshness type and filter without column or query",
            document: sources(vec![
                ("name", text("orders")),
                ("freshness", map(vec![("type", text("timestamp"))])),
            ]),
            expected_message: "/project/sources/shop.yml source freshness type and filter require column or query",
        },
        SourceErrorTestCase {
            description: "a dlt resource with write_strategy",
            document: map(vec![(
                "dlt_sources",
                Node::List(vec![map(vec![
                    ("type", text("filesystem")),
                    ("config", map(vec![("bucket_url", text("s3://orders"))])),
                    (
                        "resources",
                        Node::List(vec![map(vec![
                            ("name", text("orders")),
                            ("write_strategy", text("append")),
                        ])]),
                    ),
                ])]),
            )]),
            expected_message: "/project/sources/shop.yml dlt resource 'orders' must use dlt write_disposition, not write_strategy",
        },
    ];
    for test_case in test_cases {
        let error =
            parse_sources_document(&test_case.document, PATH).expect_err(test_case.description);
        assert_eq!(
            error.message, test_case.expected_message,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_dlt_resource_when_parsing_then_builds_a_managed_source_named_after_it() {
    let document = map(vec![(
        "dlt_sources",
        Node::List(vec![map(vec![
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
        ])]),
    )]);

    let parsed = parse_sources_document(&document, PATH).unwrap();

    assert_eq!(parsed.len(), 1);
    assert_eq!(parsed[0].loader.as_deref(), Some("orders"));
    assert!(parsed[0].managed);
    assert_eq!(parsed[0].schema, Some(text("raw")));
    assert_eq!(parsed[0].table, Some(text("orders")));
}

#[test]
fn given_freshness_durations_when_measuring_then_matches_python_duration_rules() {
    assert_eq!(freshness_minutes("15m"), Some(15));
    assert_eq!(freshness_minutes("2h"), Some(120));
    assert_eq!(freshness_minutes("1d"), Some(1_440));
    assert_eq!(freshness_minutes("1d2h"), None);
    assert_eq!(freshness_minutes("30s"), None);
    assert_eq!(freshness_minutes("0m"), None);
    assert_eq!(freshness_minutes("\u{0661}\u{0665}m"), Some(15));
}
