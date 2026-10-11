use crate::lineage::main::direct_semantic_uses::direct_semantic_uses;
use crate::lineage::models::{LineageResourceType, RichSchemaResource};

#[test]
fn unrelated_tables_are_not_built_for_rich_analysis() {
    let schema: Vec<_> = (0..254)
        .map(|index| RichSchemaResource {
            resource_type: LineageResourceType::Model,
            name: format!("orders_{index}"),
            assigned: vec![("amount".to_owned(), Some("BIGINT".to_owned()))],
            defaulted: Vec::new(),
        })
        .collect();
    for index in 0..4 {
        let expected: std::collections::HashSet<String> = (0..index)
            .map(|value| format!("__sqlbuild_model__orders_{value}"))
            .collect();
        let tables = crate::lineage::_helpers::rich_lineage::schema_tables(&schema, &expected);
        assert_eq!(
            tables
                .keys()
                .cloned()
                .collect::<std::collections::HashSet<_>>(),
            expected
        );
    }
}

#[test]
fn authored_unicode_locations_and_resource_identity_survive_native_analysis() {
    let query = "SELECT 'é' AS note FROM __ref('orders') WHERE amount > 0";
    let schema = vec![RichSchemaResource {
        resource_type: LineageResourceType::Model,
        name: "orders".to_owned(),
        assigned: vec![("amount".to_owned(), Some("BIGINT".to_owned()))],
        defaulted: Vec::new(),
    }];
    let models = vec![(
        "filtered_orders".to_owned(),
        query.to_owned(),
        format!("MODEL (description 'Filtered orders');\n\n{query}"),
    )];
    let uses = direct_semantic_uses(&schema, &models, "duckdb").expect("valid query");
    assert_eq!(uses.len(), 1);
    let usage = &uses[0];
    assert_eq!(usage.model, "filtered_orders");
    assert_eq!(usage.resource_type, LineageResourceType::Model);
    assert_eq!(usage.resource_name, "orders");
    assert_eq!(usage.column, "amount");
    assert_eq!(usage.context, "where");
    assert_eq!(usage.line, Some(3));
    assert_eq!(usage.offset, Some(47));
}
