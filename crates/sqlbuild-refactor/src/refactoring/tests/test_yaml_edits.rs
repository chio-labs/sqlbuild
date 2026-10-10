use crate::refactoring::errors::{RefactorError, RefactorErrorKind};
use crate::refactoring::tests::helpers::{
    applied, yaml_field_edits, yaml_model_edit_count, yaml_reference_edits,
};
use crate::refactoring::tests::test_types::{YamlEditsTestCase, YamlFallbackTestCase};

const SOURCES: &str = "sources:\n  - name: raw_orders\n    description: \"Feeds __ref('stg_orders').\"\n    columns:\n      - name: customer_id\n        audits:\n          relationships:\n            to: stg_orders\n            field: Order_ID\n";

#[test]
fn given_yaml_declarations_when_renaming_then_references_and_fields_are_edited()
-> Result<(), RefactorError> {
    let test_cases = [
        YamlEditsTestCase {
            description: "a quoted __ref and a bare relationships target are renamed",
            contents: SOURCES,
            plan: yaml_reference_edits,
            expected_contents: "sources:\n  - name: raw_orders\n    description: \"Feeds __ref('stg_order_lines').\"\n    columns:\n      - name: customer_id\n        audits:\n          relationships:\n            to: stg_order_lines\n            field: Order_ID\n",
        },
        YamlEditsTestCase {
            description: "a relationships field of the renamed model's column matches ignoring case",
            contents: SOURCES,
            plan: yaml_field_edits,
            expected_contents: "sources:\n  - name: raw_orders\n    description: \"Feeds __ref('stg_orders').\"\n    columns:\n      - name: customer_id\n        audits:\n          relationships:\n            to: stg_orders\n            field: order_key\n",
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

#[test]
fn given_yaml_python_cannot_plan_when_renaming_then_file_is_skipped_or_deferred() {
    let test_cases = [
        YamlFallbackTestCase {
            description: "a file PyYAML rejects is skipped",
            contents: "sources: [unclosed\n",
            expected_outcome: Ok(0),
        },
        YamlFallbackTestCase {
            description: "an anchored file defers native planning",
            contents: "a: &anchor stg_orders\nb: *anchor\n",
            expected_outcome: Err(RefactorErrorKind::Deferred),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            yaml_model_edit_count(test_case.contents),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}
