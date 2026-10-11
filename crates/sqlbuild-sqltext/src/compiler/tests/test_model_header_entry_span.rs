use crate::compiler::main::model_header_entry_span::model_header_entry_span;
use crate::compiler::tests::test_types::EntrySpanTestCase;

#[test]
fn given_model_headers_when_locating_an_entry_then_code_point_spans_match_python() {
    let test_cases = [
        EntrySpanTestCase {
            description: "a first-line entry ends before its separator",
            contents: "MODEL (cursor updated_at, description 'x');\nSELECT 1",
            expected_span: Ok(Some((7, 24))),
        },
        EntrySpanTestCase {
            description: "offsets count code points after a non-ASCII value and trim whitespace",
            contents: "MODEL (\n  description \"caf\u{e9}\"\n  cursor\tupdated_at\n);\nSELECT 1",
            expected_span: Ok(Some((31, 48))),
        },
        EntrySpanTestCase {
            description: "a nested key of the same name is skipped",
            contents: "MODEL (columns (cursor int) cursor y);\nSELECT 1",
            expected_span: Ok(Some((28, 36))),
        },
        EntrySpanTestCase {
            description: "a key without a value has no span",
            contents: "MODEL (cursor);\nSELECT 1",
            expected_span: Ok(None),
        },
        EntrySpanTestCase {
            description: "text before MODEL is not a header",
            contents: "\n\u{e9}MODEL (cursor x);",
            expected_span: Ok(None),
        },
        EntrySpanTestCase {
            description: "an unterminated string is the tokenizer's error",
            contents: "MODEL (cursor 'unterminated);\nSELECT 1",
            expected_span: Err("unterminated single-quoted string at position 7"),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            model_header_entry_span(test_case.contents, "cursor"),
            test_case.expected_span.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
