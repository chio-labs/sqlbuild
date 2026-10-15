use crate::snowflake_cost::main::metadata_only_statement::metadata_only_statement;
use crate::snowflake_cost::main::sqlbuild_query_tag::sqlbuild_query_tag;
use crate::snowflake_cost::models::QueryTag;
use crate::snowflake_cost::tests::test_types::{MetadataOnlyTestCase, QueryTagTestCase};

#[test]
fn given_snowflake_statements_when_classifying_then_detects_metadata_only_work() {
    let test_cases = [
        MetadataOnlyTestCase {
            description: "use statements need no warehouse",
            query_type: "USE_DATABASE",
            query_text: None,
            expected_metadata_only: true,
        },
        MetadataOnlyTestCase {
            description: "a column-list table is metadata only",
            query_type: "CREATE_TABLE",
            query_text: Some("CREATE TABLE t (a INT)"),
            expected_metadata_only: true,
        },
        MetadataOnlyTestCase {
            description: "a table built from a query uses the warehouse",
            query_type: "CREATE_TABLE",
            query_text: Some("CREATE TABLE t AS SELECT 1 AS a"),
            expected_metadata_only: false,
        },
        MetadataOnlyTestCase {
            description: "a materialized view uses the warehouse",
            query_type: "CREATE_VIEW",
            query_text: Some("CREATE MATERIALIZED VIEW v AS SELECT 1 AS a"),
            expected_metadata_only: false,
        },
        MetadataOnlyTestCase {
            description: "blank create text is not classified",
            query_type: "CREATE",
            query_text: Some("  "),
            expected_metadata_only: false,
        },
        MetadataOnlyTestCase {
            description: "a create-prefixed type without separator is ordinary work",
            query_type: "CREATEX",
            query_text: Some("CREATE TABLE t (a INT)"),
            expected_metadata_only: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            metadata_only_statement(test_case.query_type, test_case.query_text),
            test_case.expected_metadata_only,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_query_tags_when_parsing_then_reads_sqlbuild_attribution() {
    let test_cases = [
        QueryTagTestCase {
            description: "a version-one tag keeps non-empty strings",
            value: r#"{"app": "sqlbuild", "v": 1.0, "run_id": "r", "resource_name": ""}"#,
            expected_tag: Some(QueryTag {
                run_id: Some("r".to_owned()),
                resource_type: None,
                resource_name: None,
            }),
        },
        QueryTagTestCase {
            description: "true equals one",
            value: r#"{"app": "sqlbuild", "v": true}"#,
            expected_tag: Some(QueryTag::default()),
        },
        QueryTagTestCase {
            description: "other versions are ignored",
            value: r#"{"app": "sqlbuild", "v": 2}"#,
            expected_tag: None,
        },
        QueryTagTestCase {
            description: "non-objects are ignored",
            value: "[]",
            expected_tag: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            sqlbuild_query_tag(test_case.value),
            test_case.expected_tag,
            "{}",
            test_case.description
        );
    }
}
