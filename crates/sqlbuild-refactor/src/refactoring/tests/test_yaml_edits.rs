use crate::refactoring::errors::RefactorError;
use crate::refactoring::tests::helpers::{
    applied, owned_span_pair, yaml_field_edits, yaml_reference_edits, yaml_spans,
};
use crate::refactoring::tests::test_types::{YamlEditsTestCase, YamlSpansTestCase};

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
fn given_yaml_edge_cases_when_renaming_then_python_edits_are_kept() -> Result<(), RefactorError> {
    let test_cases = [
        YamlSpansTestCase {
            description: "a file PyYAML rejects is skipped",
            contents: "sources: [unclosed\n",
            expected_spans: (&[], &[]),
        },
        YamlSpansTestCase {
            description: "an anchored target is renamed through its alias",
            contents: "a: &anchor stg_orders\nb: *anchor\nsources:\n  - audits:\n      relationships:\n        to: *anchor\n",
            expected_spans: (&[(11, 21, "stg_orders")], &[]),
        },
        YamlSpansTestCase {
            description: "an aliased string is edited once per visit and an aliased relationship is followed",
            contents: "base: &rel\n  to: stg_orders\n  field: Order_ID\nsources:\n  - d: &d \"x __ref('stg_orders')\"\n    audits:\n      relationships: *rel\n  - e: *d\n",
            expected_spans: (
                &[
                    (75, 85, "stg_orders"),
                    (75, 85, "stg_orders"),
                    (17, 27, "stg_orders"),
                ],
                &[(37, 45, "Order_ID")],
            ),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            yaml_spans(test_case.contents)?,
            owned_span_pair(test_case.expected_spans),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
