use crate::refactoring::errors::RefactorError;
use crate::refactoring::tests::helpers::{
    applied, fact_orders_migration_entry, header_fact_column_edits, header_fact_model_edits,
    migrated_column_edits, schema_fact_column_edits, schema_fact_model_edits,
    yaml_fact_column_edits, yaml_fact_model_edits,
};
use crate::refactoring::tests::test_types::ContentEditsTestCase;

#[test]
fn given_declarations_when_renaming_then_python_planner_edits_are_kept() -> Result<(), RefactorError>
{
    let test_cases = [
        ContentEditsTestCase {
            description: "relationships target written as a reference",
            contents: "seeds:\n  - name: customers\n    columns:\n      - name: customer_id\n        audits:\n          - relationships:\n              to: __ref(\"fact_orders\")\n              field: customer_id\n",
            plan: yaml_fact_model_edits,
            expected_contents: "seeds:\n  - name: customers\n    columns:\n      - name: customer_id\n        audits:\n          - relationships:\n              to: __ref(\"order_facts\")\n              field: customer_id\n",
        },
        ContentEditsTestCase {
            description: "bare relationships target in a flow mapping",
            contents: "audits:\n  - relationships: {to: fact_orders, field: customer_id}\n",
            plan: yaml_fact_model_edits,
            expected_contents: "audits:\n  - relationships: {to: order_facts, field: customer_id}\n",
        },
        ContentEditsTestCase {
            description: "reference inside an escaped double-quoted expression",
            contents: "audits:\n  - expression_is_true: {expression: \"id IN (SELECT id FROM __ref(\\\"fact_orders\\\"))\"}\n",
            plan: yaml_fact_model_edits,
            expected_contents: "audits:\n  - expression_is_true: {expression: \"id IN (SELECT id FROM __ref(\\\"order_facts\\\"))\"}\n",
        },
        ContentEditsTestCase {
            description: "similar names and descriptions are left alone",
            contents: "sources:\n  - name: raw\n    description: fact_orders feed\n    audits:\n      - relationships: {to: fact_orders_daily, field: id}\n",
            plan: yaml_fact_model_edits,
            expected_contents: "sources:\n  - name: raw\n    description: fact_orders feed\n    audits:\n      - relationships: {to: fact_orders_daily, field: id}\n",
        },
        ContentEditsTestCase {
            description: "YAML field of a relationship to the model",
            contents: "audits:\n  - relationships: {to: '__ref(\"fact_orders\")', field: amount}\n",
            plan: yaml_fact_column_edits,
            expected_contents: "audits:\n  - relationships: {to: '__ref(\"fact_orders\")', field: revenue}\n",
        },
        ContentEditsTestCase {
            description: "YAML field of a relationship to another model",
            contents: "audits:\n  - relationships: {to: '__ref(\"customers\")', field: amount}\n",
            plan: yaml_fact_column_edits,
            expected_contents: "audits:\n  - relationships: {to: '__ref(\"customers\")', field: amount}\n",
        },
        ContentEditsTestCase {
            description: "MODEL header quoted SQL and bare relationships target",
            contents: "MODEL (\n  audits [expression_is_true (expression \"id IN (SELECT id FROM __ref('fact_orders'))\")],\n  columns (\n    id (audits [relationships (to fact_orders, field id)]),\n  ),\n);\nSELECT order_id FROM orders\n",
            plan: header_fact_model_edits,
            expected_contents: "MODEL (\n  audits [expression_is_true (expression \"id IN (SELECT id FROM __ref('order_facts'))\")],\n  columns (\n    id (audits [relationships (to order_facts, field id)]),\n  ),\n);\nSELECT order_id FROM orders\n",
        },
        ContentEditsTestCase {
            description: "MODEL header field of a referenced relationship target",
            contents: "MODEL (\n  columns (\n    id (audits [relationships (to __ref(\"fact_orders\"), field amount)]),\n  ),\n);\nSELECT order_id FROM orders\n",
            plan: header_fact_column_edits,
            expected_contents: "MODEL (\n  columns (\n    id (audits [relationships (to __ref(\"fact_orders\"), field revenue)]),\n  ),\n);\nSELECT order_id FROM orders\n",
        },
        ContentEditsTestCase {
            description: "bare target and quoted SQL in every SCHEMA of a file",
            contents: "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships (to fact_orders, field id)]),\n  ),\n);\n\nSCHEMA (\n  name order_totals,\n  audits [expression_is_true (expression \"total > (SELECT 0 FROM __ref('fact_orders') LIMIT 1)\")],\n);\n",
            plan: schema_fact_model_edits,
            expected_contents: "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships (to order_facts, field id)]),\n  ),\n);\n\nSCHEMA (\n  name order_totals,\n  audits [expression_is_true (expression \"total > (SELECT 0 FROM __ref('order_facts') LIMIT 1)\")],\n);\n",
        },
        ContentEditsTestCase {
            description: "SCHEMA field of a relationship to the model",
            contents: "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships (to __ref(\"fact_orders\"), field amount)]),\n  ),\n);\n",
            plan: schema_fact_column_edits,
            expected_contents: "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships (to __ref(\"fact_orders\"), field revenue)]),\n  ),\n);\n",
        },
        ContentEditsTestCase {
            description: "declared column gains migrate_from before its metadata",
            contents: "MODEL (\n  columns (\n    amount (nullable false),\n  ),\n);\nSELECT order_id, amount FROM orders\n",
            plan: migrated_column_edits,
            expected_contents: "MODEL (\n  columns (\n    revenue (migrate_from amount, nullable false),\n  ),\n);\nSELECT order_id, amount FROM orders\n",
        },
        ContentEditsTestCase {
            description: "bare declared column gains a migrate_from block",
            contents: "MODEL (\n  columns (amount),\n);\nSELECT order_id, amount FROM orders\n",
            plan: migrated_column_edits,
            expected_contents: "MODEL (\n  columns (revenue (migrate_from amount)),\n);\nSELECT order_id, amount FROM orders\n",
        },
        ContentEditsTestCase {
            description: "undeclared column gets a new columns entry",
            contents: "MODEL (\n  materialized incremental,\n);\nSELECT order_id, amount FROM orders\n",
            plan: migrated_column_edits,
            expected_contents: "MODEL (\n  columns (revenue (migrate_from amount)),\n  materialized incremental,\n);\nSELECT order_id, amount FROM orders\n",
        },
        ContentEditsTestCase {
            description: "column-valued config follows the column",
            contents: "MODEL (\n  unique_key [order_id, amount],\n);\nSELECT order_id, amount FROM orders\n",
            plan: migrated_column_edits,
            expected_contents: "MODEL (\n  columns (revenue (migrate_from amount)),\n  unique_key [order_id, revenue],\n);\nSELECT order_id, amount FROM orders\n",
        },
        ContentEditsTestCase {
            description: "cursor_inputs keys and relationships targets follow the model",
            contents: "MODEL (\n  cursor_inputs (\n    fact_orders ordered_at,\n  ),\n  columns (\n    order_id (audits [relationships (to fact_orders, field order_id)]),\n  ),\n);\nSELECT order_id, amount FROM orders\n",
            plan: header_fact_model_edits,
            expected_contents: "MODEL (\n  cursor_inputs (\n    order_facts ordered_at,\n  ),\n  columns (\n    order_id (audits [relationships (to order_facts, field order_id)]),\n  ),\n);\nSELECT order_id, amount FROM orders\n",
        },
        ContentEditsTestCase {
            description: "descriptions naming the model are left alone",
            contents: "MODEL (\n  description \"fact_orders summary\",\n);\nSELECT order_id, amount FROM orders\n",
            plan: header_fact_model_edits,
            expected_contents: "MODEL (\n  description \"fact_orders summary\",\n);\nSELECT order_id, amount FROM orders\n",
        },
        ContentEditsTestCase {
            description: "multi-line header gets its own line",
            contents: "MODEL (\n  materialized table,\n);\nSELECT order_id, amount FROM orders\n",
            plan: fact_orders_migration_entry,
            expected_contents: "MODEL (\n  migrate_from fact_orders,\n  materialized table,\n);\nSELECT order_id, amount FROM orders\n",
        },
        ContentEditsTestCase {
            description: "empty header is expanded",
            contents: "MODEL ();\nSELECT order_id, amount FROM orders\n",
            plan: fact_orders_migration_entry,
            expected_contents: "MODEL (\n  migrate_from fact_orders,\n);\nSELECT order_id, amount FROM orders\n",
        },
    ];
    for test_case in test_cases {
        let edits = (test_case.plan)(test_case.contents)?;
        assert_eq!(
            applied(test_case.contents, &edits)?,
            test_case.expected_contents,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
