use crate::refactoring::errors::RefactorError;
use crate::refactoring::tests::helpers::{
    applied, consumer_model_edits, described, inserted_entry, owner_column_edits,
    owner_header_parts, schema_field_edits, schema_model_edits,
};
use crate::refactoring::tests::test_types::{
    HeaderEditsTestCase, HeaderPartsTestCase, InsertEntryTestCase,
};

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
            description: "newline-separated columns entries without commas are found",
            contents: "MODEL (\n  materialized incremental,\n  columns (\n    amount (type INT)\n    order_id (type VARCHAR)\n  ),\n);\n\nSELECT 1\n",
            plan: owner_column_edits,
            expected_edits: &[
                "5:5 header \"order_id\" -> \"order_key\"",
                "5:15 migration \"\" -> \"migrate_from order_id\"",
            ],
            expected_contents: "MODEL (\n  materialized incremental,\n  columns (\n    amount (type INT)\n    order_key (migrate_from order_id, type VARCHAR)\n  ),\n);\n\nSELECT 1\n",
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

#[test]
fn given_owner_header_when_renaming_column_then_declarations_and_audit_arguments_follow()
-> Result<(), RefactorError> {
    let test_cases = [
        HeaderPartsTestCase {
            description: "a comma-less column declaration is renamed instead of left for a hand edit",
            contents: "MODEL (\n  columns (\n    order_id (type VARCHAR)\n    is_flagged (type BOOLEAN)\n  ),\n);\nSELECT 1\n",
            expected_edits: &["4:5 header \"is_flagged\" -> \"is_marked\""],
            expected_manual: &[],
        },
        HeaderPartsTestCase {
            description: "column and model audit arguments rename column references, not string literals",
            contents: "MODEL (\n  columns (\n    is_flagged (audits [flag_check (where_condition \"is_flagged AND 'is_flagged' <> ''\")]),\n  ),\n  audits [flag_check (name \"orders_flag\", where_condition \"NOT is_flagged\")],\n);\nSELECT 1\n",
            expected_edits: &[
                "3:5 header \"is_flagged\" -> \"is_marked\"",
                "3:54 header \"is_flagged\" -> \"is_marked\"",
                "5:64 header \"is_flagged\" -> \"is_marked\"",
            ],
            expected_manual: &[],
        },
        HeaderPartsTestCase {
            description: "an audit argument that is not a parseable expression is listed for a hand edit",
            contents: "MODEL (\n  audits [flag_check (where_condition \"is_flagged ((\")],\n);\nSELECT 1\n",
            expected_edits: &[],
            expected_manual: &[
                "2:40 this audit argument mentions is_flagged but is not a SQL expression SQLBuild can parse; update it by hand",
            ],
        },
        HeaderPartsTestCase {
            description: "a qualified reference the analysis cannot resolve is listed for a hand edit",
            contents: "MODEL (\n  audits [flag_check (where_condition \"NOT orders.is_flagged\")],\n);\nSELECT 1\n",
            expected_edits: &[],
            expected_manual: &[
                "2:44 cannot tell whether is_flagged in this audit argument is the renamed column; update it by hand",
            ],
        },
        HeaderPartsTestCase {
            description: "a subquery reading another model keeps its own column",
            contents: "MODEL (\n  audits [flag_check (where_condition 'is_flagged IN (SELECT is_flagged FROM __ref(\"vip_flags\"))')],\n);\nSELECT 1\n",
            expected_edits: &["2:40 header \"is_flagged\" -> \"is_marked\""],
            expected_manual: &[],
        },
        HeaderPartsTestCase {
            description: "a subquery reading the audited model renames its column too",
            contents: "MODEL (\n  audits [flag_check (where_condition 'is_flagged IN (SELECT is_flagged FROM __ref(\"orders\"))')],\n);\nSELECT 1\n",
            expected_edits: &[
                "2:40 header \"is_flagged\" -> \"is_marked\"",
                "2:62 header \"is_flagged\" -> \"is_marked\"",
            ],
            expected_manual: &[],
        },
        HeaderPartsTestCase {
            description: "a subquery reading a model of unknown columns is not renamed",
            contents: "MODEL (\n  audits [flag_check (where_condition 'is_flagged IN (SELECT is_flagged FROM __ref(\"unknown_flags\"))')],\n);\nSELECT 1\n",
            expected_edits: &[],
            expected_manual: &[
                "2:40 this audit argument reads unknown_flags, whose columns SQLBuild does not know, so is_flagged here is not renamed; update it by hand",
                "2:62 this audit argument reads unknown_flags, whose columns SQLBuild does not know, so is_flagged here is not renamed; update it by hand",
            ],
        },
        HeaderPartsTestCase {
            description: "an argument the audit quotes as a string is listed, not renamed",
            contents: "MODEL (\n  audits [prefix_check (prefix \"is_flagged\")],\n);\nSELECT 1\n",
            expected_edits: &[],
            expected_manual: &[
                "2:33 audit prefix_check quotes argument prefix as a string, so is_flagged here is not renamed; update it by hand if it names the column",
            ],
        },
        HeaderPartsTestCase {
            description: "an argument of an audit with no SQL definition is listed, not renamed",
            contents: "MODEL (\n  audits [python_check (where_condition \"NOT is_flagged\")],\n);\nSELECT 1\n",
            expected_edits: &[],
            expected_manual: &[
                "2:46 no SQL definition of audit python_check shows whether argument where_condition is SQL, so is_flagged here is not renamed; update it by hand if it names the column",
            ],
        },
        HeaderPartsTestCase {
            description: "audit option values and list literals are not audit arguments",
            contents: "MODEL (\n  audits [accepted_values (name \"is_flagged\", values [\"is_flagged\"])],\n);\nSELECT 1\n",
            expected_edits: &[],
            expected_manual: &[
                "2:34 the MODEL header mentions is_flagged here; update it by hand",
                "2:56 the MODEL header mentions is_flagged here; update it by hand",
            ],
        },
    ];
    for test_case in test_cases {
        let (edits, manual) = owner_header_parts(test_case.contents)?;
        assert_eq!(edits, test_case.expected_edits, "{}", test_case.description);
        assert_eq!(
            manual, test_case.expected_manual,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
