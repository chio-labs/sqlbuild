use crate::compiler::main::model_header_matching::match_batch;
use crate::compiler::tests::test_types::ModelHeaderMatchTestCase;

#[test]
fn given_model_files_when_matching_headers_then_offsets_follow_the_python_pattern() {
    let test_cases = [
        ModelHeaderMatchTestCase {
            description: "simple header",
            contents: "MODEL (name orders);\nSELECT 1",
            expected_offsets: Some((7, 18, 21)),
        },
        ModelHeaderMatchTestCase {
            description: "leading whitespace and spaced terminator",
            contents: " \n MODEL\t( a ) \n ; \n SELECT 1",
            expected_offsets: Some((10, 13, 21)),
        },
        ModelHeaderMatchTestCase {
            description: "closing parenthesis not followed by a semicolon stays in the header",
            contents: "MODEL (columns (id INT));SELECT 1",
            expected_offsets: Some((7, 23, 25)),
        },
        ModelHeaderMatchTestCase {
            description: "quoted closing parenthesis and semicolon stay in the header",
            contents: "MODEL (description 'a);b');SELECT 1",
            expected_offsets: Some((7, 25, 27)),
        },
        ModelHeaderMatchTestCase {
            description: "unclosed quote runs to the next parenthesis",
            contents: "MODEL (description 'open);SELECT 1",
            expected_offsets: Some((7, 24, 26)),
        },
        ModelHeaderMatchTestCase {
            description: "escaped quote inside a string",
            contents: "MODEL (description \"a\\\"b\");SELECT 1",
            expected_offsets: Some((7, 25, 27)),
        },
        ModelHeaderMatchTestCase {
            description: "non ascii offsets are code points",
            contents: "MODEL (description 'caf\u{e9}')\u{a0};\u{3000}SELECT 1",
            expected_offsets: Some((7, 25, 29)),
        },
        ModelHeaderMatchTestCase {
            description: "missing terminator",
            contents: "MODEL (name orders)\nSELECT 1",
            expected_offsets: None,
        },
        ModelHeaderMatchTestCase {
            description: "trailing lone backslash",
            contents: "MODEL (name orders\\",
            expected_offsets: None,
        },
        ModelHeaderMatchTestCase {
            description: "lowercase keyword",
            contents: "model (name orders);",
            expected_offsets: None,
        },
        ModelHeaderMatchTestCase {
            description: "empty file",
            contents: "",
            expected_offsets: None,
        },
    ];

    for test_case in test_cases {
        let actual = match_batch(&[test_case.contents.to_string()])[0];
        assert_eq!(
            actual, test_case.expected_offsets,
            "{}",
            test_case.description
        );
    }
}
