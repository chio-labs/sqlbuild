use crate::refactoring::_helpers::yaml_edits::{yaml_column_edits, yaml_model_edits};
use crate::refactoring::models::{DiscoveredFile, RefactorError, RefactorErrorKind, TextEdit};
use crate::refactoring::tests::helpers::applied;
use crate::refactoring::tests::test_types::YamlEditsTestCase;

const SOURCES: &str = "sources:\n  - name: raw_orders\n    description: \"Feeds __ref('stg_orders').\"\n    columns:\n      - name: customer_id\n        audits:\n          relationships:\n            to: stg_orders\n            field: Order_ID\n";

fn file(contents: &str) -> Vec<DiscoveredFile> {
    vec![DiscoveredFile {
        path: "sources/raw.yml".to_owned(),
        contents: contents.to_owned(),
    }]
}

fn only_edits(edits: Vec<(String, TextEdit)>) -> Vec<TextEdit> {
    edits.into_iter().map(|(_, edit)| edit).collect()
}

#[test]
fn given_yaml_declarations_when_renaming_then_references_and_fields_are_edited()
-> Result<(), RefactorError> {
    let test_cases = [
        YamlEditsTestCase {
            description: "a quoted __ref and a bare relationships target are renamed",
            contents: SOURCES,
            expected_contents: "sources:\n  - name: raw_orders\n    description: \"Feeds __ref('stg_order_lines').\"\n    columns:\n      - name: customer_id\n        audits:\n          relationships:\n            to: stg_order_lines\n            field: Order_ID\n",
        },
        YamlEditsTestCase {
            description: "a relationships field of the renamed model's column matches ignoring case",
            contents: SOURCES,
            expected_contents: "sources:\n  - name: raw_orders\n    description: \"Feeds __ref('stg_orders').\"\n    columns:\n      - name: customer_id\n        audits:\n          relationships:\n            to: stg_orders\n            field: order_key\n",
        },
    ];
    let edits_by_case = [
        only_edits(yaml_model_edits(
            &file(SOURCES),
            "stg_orders",
            "stg_order_lines",
        )?),
        only_edits(yaml_column_edits(
            &file(SOURCES),
            "stg_orders",
            "order_id",
            "order_key",
        )?),
    ];
    for (test_case, edits) in test_cases.into_iter().zip(edits_by_case) {
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
fn given_yaml_python_rejects_when_renaming_then_file_is_skipped() -> Result<(), RefactorError> {
    let edits = yaml_model_edits(&file("sources: [unclosed\n"), "stg_orders", "x")?;
    assert!(edits.is_empty());
    Ok(())
}

#[test]
fn given_anchored_yaml_when_renaming_then_native_planning_defers() {
    let result = yaml_model_edits(
        &file("a: &anchor stg_orders\nb: *anchor\n"),
        "stg_orders",
        "x",
    );
    assert_eq!(
        result.map_err(|error| error.kind),
        Err(RefactorErrorKind::Deferred)
    );
}
