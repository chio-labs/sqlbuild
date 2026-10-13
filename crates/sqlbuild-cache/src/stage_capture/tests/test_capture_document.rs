use sqlbuild_core::json::models::JsonValue;

use crate::stage_capture::main::capture_sort_key::capture_sort_key;
use crate::stage_capture::models::CaptureDocument;
use crate::stage_capture::tests::helpers::{integer, text};
use crate::stage_capture::tests::test_types::{DocumentTestCase, SortKeyTestCase};

#[test]
fn given_shared_nodes_and_root_when_writing_document_then_matches_python_writer() {
    let test_cases = [
        DocumentTestCase {
            description: "a document without shared nodes is the indented root",
            shared: &[],
            root: JsonValue::Object(vec![(
                "a".to_owned(),
                JsonValue::Array(vec![integer(1), text("\u{e9}")]),
            )]),
            expected_document: "{\n \"a\": [\n  1,\n  \"\u{e9}\"\n ]\n}\n",
        },
        DocumentTestCase {
            description: "shared nodes precede the compact root",
            shared: &[("d1", "[1]"), ("d2", "\"x\"")],
            root: JsonValue::Object(vec![(
                "a".to_owned(),
                JsonValue::Object(vec![("__shared__".to_owned(), text("d1"))]),
            )]),
            expected_document: "{\"__shared_nodes__\": {\n\"d1\": [1],\n\"d2\": \"x\"\n},\n\"__capture__\": {\"a\":{\"__shared__\":\"d1\"}}\n}\n",
        },
    ];

    for test_case in test_cases {
        let mut document = CaptureDocument::default();
        let mut written = String::new();
        for (digest, node) in test_case.shared {
            written.push_str(&document.shared_chunk(digest, node));
        }
        written.push_str(&document.final_chunk(&test_case.root).unwrap_or_default());

        assert_eq!(
            written, test_case.expected_document,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_item_when_keying_for_sort_then_matches_python_sort_key() {
    let test_cases = [SortKeyTestCase {
        description: "keys are sorted, separators spaced and noise masked",
        item: JsonValue::Object(vec![
            ("b".to_owned(), integer(1)),
            (
                "a".to_owned(),
                JsonValue::Array(vec![integer(2), text("x 20261012T223835Z_81de82a3e779")]),
            ),
        ]),
        expected_key: "{\"a\": [2, \"x <invocation-id>\"], \"b\": 1}",
    }];

    for test_case in test_cases {
        let key = capture_sort_key(&test_case.item).unwrap_or_default();

        assert_eq!(key, test_case.expected_key, "{}", test_case.description);
    }
}
