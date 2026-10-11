use crate::lineage::main::direct_semantic_uses::direct_semantic_uses;
use crate::lineage::models::{LineageResourceType, RichSchemaResource};
use crate::lineage::tests::test_types::{SchemaFilterTestCase, SemanticUseTestCase};

#[test]
fn given_unrelated_tables_when_building_rich_schema_then_only_referenced_tables_are_built() {
    let test_cases = [
        SchemaFilterTestCase {
            description: "no references",
            referenced: 0,
            expected_tables: 0,
        },
        SchemaFilterTestCase {
            description: "one upstream",
            referenced: 1,
            expected_tables: 1,
        },
        SchemaFilterTestCase {
            description: "three upstreams",
            referenced: 3,
            expected_tables: 3,
        },
    ];
    for test_case in test_cases {
        let schema: Vec<RichSchemaResource> = (0..254)
            .map(|index| RichSchemaResource {
                resource_type: LineageResourceType::Model,
                name: format!("orders_{index}"),
                assigned: vec![("amount".to_owned(), Some("BIGINT".to_owned()))],
                defaulted: Vec::new(),
            })
            .collect();
        let expected: std::collections::HashSet<String> = (0..test_case.referenced)
            .map(|value| format!("__sqlbuild_model__orders_{value}"))
            .collect();
        let tables = crate::lineage::_helpers::rich_lineage::schema_tables(&schema, &expected);
        assert_eq!(
            tables.len(),
            test_case.expected_tables,
            "{}",
            test_case.description
        );
        assert_eq!(
            tables
                .keys()
                .cloned()
                .collect::<std::collections::HashSet<_>>(),
            expected,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_authored_unicode_when_analyzing_semantic_uses_then_locations_and_resources_are_preserved()
{
    let test_cases = [SemanticUseTestCase {
        description: "Unicode before a unique predicate column",
        query: "SELECT 'é' AS note FROM __ref('orders') WHERE amount > 0",
        expected_count: 1,
        expected_line: 3,
        expected_offset: 47,
    }];
    for test_case in test_cases {
        let schema = vec![RichSchemaResource {
            resource_type: LineageResourceType::Model,
            name: "orders".to_owned(),
            assigned: vec![("amount".to_owned(), Some("BIGINT".to_owned()))],
            defaulted: Vec::new(),
        }];
        let models = vec![(
            "filtered_orders".to_owned(),
            test_case.query.to_owned(),
            format!(
                "MODEL (description 'Filtered orders');\n\n{}",
                test_case.query
            ),
        )];
        let uses = direct_semantic_uses(&schema, &models, "duckdb").expect("valid query");
        assert_eq!(
            uses.len(),
            test_case.expected_count,
            "{}",
            test_case.description
        );
        let usage = &uses[0];
        assert_eq!(usage.model, "filtered_orders", "{}", test_case.description);
        assert_eq!(
            usage.resource_type,
            LineageResourceType::Model,
            "{}",
            test_case.description
        );
        assert_eq!(usage.resource_name, "orders", "{}", test_case.description);
        assert_eq!(usage.column, "amount", "{}", test_case.description);
        assert_eq!(usage.context, "where", "{}", test_case.description);
        assert_eq!(
            usage.line,
            Some(test_case.expected_line),
            "{}",
            test_case.description
        );
        assert_eq!(
            usage.offset,
            Some(test_case.expected_offset),
            "{}",
            test_case.description
        );
    }
}
