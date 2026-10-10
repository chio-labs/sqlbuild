use crate::refactoring::_helpers::chars::chars;
use crate::refactoring::_helpers::header_edits::{
    column_config_edits, column_entry_edits, header_tokens, insert_header_entry_edit,
    model_name_header_edits, schema_column_edits, schema_model_name_edits,
};
use crate::refactoring::models::{RefactorError, TextEdit};
use crate::refactoring::tests::helpers::{applied, described, python};
use crate::refactoring::tests::test_types::{HeaderEditsTestCase, InsertEntryTestCase};

const CONSUMER: &str = "MODEL (\n  description 'Reads __ref(\"stg_orders\") rows.',\n  cursor_inputs (stg_orders (order_date)),\n  relationships (to stg_orders, field order_id),\n  materialized incremental,\n);\n\nSELECT 1\n";
const OWNER: &str = "MODEL (\n  materialized incremental,\n  unique_key order_id,\n  columns (\n    order_id (description 'Order key.'),\n    amount,\n  ),\n);\n\nSELECT 1\n";
const SCHEMA_FILE: &str = "SCHEMA (\n  name orders_schema,\n  relationships (to stg_orders, field order_id),\n);\nXSCHEMA (relationships (to stg_orders));\n";

fn owner_column_edits(
    contents: &str,
    old: &str,
    new: &str,
) -> Result<Vec<TextEdit>, RefactorError> {
    let text = chars(contents);
    let tokens = header_tokens(contents, &text)?.unwrap_or_default();
    let mut edits = column_config_edits(&text, &tokens, old, new);
    edits.extend(column_entry_edits(&text, &tokens, (old, new), true).unwrap_or_default());
    Ok(edits)
}

#[test]
fn given_headers_when_renaming_then_token_exact_edits_are_planned() -> Result<(), RefactorError> {
    let consumer = chars(CONSUMER);
    let schema = chars(SCHEMA_FILE);
    let test_cases = [
        HeaderEditsTestCase {
            description: "a renamed model in cursor_inputs, a bare relationships target and quoted SQL",
            contents: CONSUMER,
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
            expected_edits: &["3:21 header \"stg_orders\" -> \"stg_order_lines\""],
            expected_contents: "SCHEMA (\n  name orders_schema,\n  relationships (to stg_order_lines, field order_id),\n);\nXSCHEMA (relationships (to stg_orders));\n",
        },
    ];
    let edits_by_case: [Vec<TextEdit>; 3] = [
        model_name_header_edits(CONSUMER, &consumer, "stg_orders", "stg_order_lines")?,
        owner_column_edits(OWNER, "order_id", "order_key")?,
        schema_model_name_edits(
            SCHEMA_FILE,
            &schema,
            ("stg_orders", "stg_order_lines"),
            python(),
        )?,
    ];
    for (test_case, edits) in test_cases.into_iter().zip(edits_by_case) {
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
fn given_schema_relationship_when_renaming_upstream_column_then_field_is_renamed()
-> Result<(), RefactorError> {
    let edits = schema_column_edits(
        SCHEMA_FILE,
        &chars(SCHEMA_FILE),
        "stg_orders",
        ("order_id", "order_key"),
        python(),
    )?;
    assert_eq!(
        described(&edits),
        ["3:39 header \"order_id\" -> \"order_key\""]
    );
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
        let text = chars(test_case.contents);
        let edit = insert_header_entry_edit(
            test_case.contents,
            &text,
            "migrate_from old_orders",
            "migrate_from old_orders",
        );
        let result = match edit {
            Some(edit) => Some(applied(test_case.contents, &[edit])?),
            None => None,
        };
        assert_eq!(
            result.as_deref(),
            test_case.expected_contents,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
