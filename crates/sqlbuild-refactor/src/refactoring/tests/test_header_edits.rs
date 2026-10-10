use crate::refactoring::errors::RefactorError;
use crate::refactoring::tests::helpers::{
    applied, consumer_model_edits, described, inserted_entry, owner_column_edits,
    schema_field_edits, schema_model_edits,
};
use crate::refactoring::tests::test_types::{HeaderEditsTestCase, InsertEntryTestCase};

const CONSUMER: &str = "MODEL (\n  description 'Reads __ref(\"stg_orders\") rows.',\n  cursor_inputs (stg_orders (order_date)),\n  relationships (to stg_orders, field order_id),\n  materialized incremental,\n);\n\nSELECT 1\n";
const OWNER: &str = "MODEL (\n  materialized incremental,\n  unique_key order_id,\n  columns (\n    order_id (description 'Order key.'),\n    amount,\n  ),\n);\n\nSELECT 1\n";
const SCHEMA_FILE: &str = "SCHEMA (\n  name orders_schema,\n  relationships (to stg_orders, field order_id),\n);\nXSCHEMA (relationships (to stg_orders));\n";

#[test]
fn given_headers_when_renaming_then_token_exact_edits_are_planned() -> Result<(), RefactorError> {
    let test_cases = [
        HeaderEditsTestCase {
            description: "a renamed model in cursor_inputs, a bare relationships target and quoted SQL",
            contents: CONSUMER,
            plan: consumer_model_edits,
            expected_edits: &[
                "3:18 header \"stg_orders\" -> \"stg_order_lines\"",
                "4:21 header \"stg_orders\" -> \"stg_order_lines\"",
                "2:29 reference \"stg_orders\" -> \"stg_order_lines\"",
            ],
            expected_contents: "MODEL (\n  description 'Reads __ref(\"stg_order_lines\") rows.',\n  cursor_inputs (stg_order_lines (order_date)),\n  relationships (to stg_order_lines, field order_id),\n  materialized incremental,\n);\n\nSELECT 1\n",
        },
        HeaderEditsTestCase {
            description: "a renamed key column with metadata gains migrate_from inside its parentheses",
            contents: OWNER,
            plan: owner_column_edits,
            expected_edits: &[
                "3:14 header \"order_id\" -> \"order_key\"",
                "5:5 header \"order_id\" -> \"order_key\"",
                "5:15 migration \"\" -> \"migrate_from order_id\"",
            ],
            expected_contents: "MODEL (\n  materialized incremental,\n  unique_key order_key,\n  columns (\n    order_key (migrate_from order_id, description 'Order key.'),\n    amount,\n  ),\n);\n\nSELECT 1\n",
        },
        HeaderEditsTestCase {
            description: "a SCHEMA header target is renamed; a longer keyword is not a SCHEMA header",
            contents: SCHEMA_FILE,
            plan: schema_model_edits,
            expected_edits: &["3:21 header \"stg_orders\" -> \"stg_order_lines\""],
            expected_contents: "SCHEMA (\n  name orders_schema,\n  relationships (to stg_order_lines, field order_id),\n);\nXSCHEMA (relationships (to stg_orders));\n",
        },
        HeaderEditsTestCase {
            description: "a SCHEMA relationship field follows its upstream column",
            contents: SCHEMA_FILE,
            plan: schema_field_edits,
            expected_edits: &["3:39 header \"order_id\" -> \"order_key\""],
            expected_contents: "SCHEMA (\n  name orders_schema,\n  relationships (to stg_orders, field order_key),\n);\nXSCHEMA (relationships (to stg_orders));\n",
        },
    ];
    for test_case in test_cases {
        let edits = (test_case.plan)(test_case.contents)?;
        assert_eq!(
            described(&edits),
            test_case.expected_edits,
            "{}",
            test_case.description
        );
        assert_eq!(
            applied(test_case.contents, &edits)?,
            test_case.expected_contents,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_header_layouts_when_inserting_entry_then_python_spacing_is_kept()
-> Result<(), RefactorError> {
    let test_cases = [
        InsertEntryTestCase {
            description: "a multi-line header gains a first line with its indentation",
            contents: "MODEL (\n    materialized table,\n);\nSELECT 1",
            expected_contents: Some(
                "MODEL (\n    migrate_from old_orders,\n    materialized table,\n);\nSELECT 1",
            ),
        },
        InsertEntryTestCase {
            description: "a one-line header gains a leading entry",
            contents: "MODEL (materialized table);\nSELECT 1",
            expected_contents: Some(
                "MODEL (migrate_from old_orders, materialized table);\nSELECT 1",
            ),
        },
        InsertEntryTestCase {
            description: "an empty header becomes a multi-line header",
            contents: "MODEL ();\nSELECT 1",
            expected_contents: Some("MODEL (\n  migrate_from old_orders,\n);\nSELECT 1"),
        },
        InsertEntryTestCase {
            description: "a file without a header gets no edit",
            contents: "SELECT 1",
            expected_contents: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            inserted_entry(test_case.contents)?.as_deref(),
            test_case.expected_contents,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
