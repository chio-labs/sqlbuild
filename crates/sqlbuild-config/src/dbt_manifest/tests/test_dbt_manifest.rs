use crate::dbt_manifest::errors::ManifestError;
use crate::dbt_manifest::main::parse_manifest_model::parse_manifest_model;
use crate::dbt_manifest::models::{NodeChecksum, ParsedModel};
use crate::dbt_manifest::tests::helpers::node;
use crate::dbt_manifest::tests::test_types::ModelTestCase;

#[test]
fn given_manifest_model_nodes_when_parsing_then_matches_python_rules() {
    let test_cases = [
        ModelTestCase {
            description: "relation from namespace and alias, nested checksum, compiled sql fallback",
            node: node(
                &[
                    ("package_name", "analytics"),
                    ("name", "orders"),
                    ("database", ""),
                    ("schema", "main"),
                    ("alias", "orders_v2"),
                    ("raw_code", ""),
                    ("compiled_code", "select 1"),
                ],
                NodeChecksum::Nested(Some("abc".to_owned())),
            ),
            expected_result: Ok(ParsedModel {
                package_name: "analytics".to_owned(),
                name: "orders".to_owned(),
                database: None,
                schema: Some("main".to_owned()),
                alias: Some("orders_v2".to_owned()),
                node_checksum: Some("abc".to_owned()),
                relation_name: "main.orders_v2".to_owned(),
                fqn: vec!["analytics".to_owned(), "orders".to_owned()],
                query_sql: "select 1".to_owned(),
                depends_on: vec!["model.a.b".to_owned()],
            }),
        },
        ModelTestCase {
            description: "empty name is rejected",
            node: node(
                &[("package_name", "analytics"), ("name", "")],
                NodeChecksum::Other,
            ),
            expected_result: Err(ManifestError {
                code: "C211",
                message: "Invalid dbt manifest: model name is required".to_owned(),
                help: None,
            }),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            parse_manifest_model(&test_case.node),
            test_case.expected_result,
            "{}",
            test_case.description
        );
    }
}
