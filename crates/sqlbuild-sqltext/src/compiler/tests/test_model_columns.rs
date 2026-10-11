use crate::compiler::main::header_word_value::header_word_value;
use crate::compiler::main::model_header_column_locations::model_header_column_locations;
use crate::compiler::main::model_header_columns::model_header_columns;
use crate::compiler::main::model_output_columns::model_output_columns;
use crate::compiler::models::{HeaderColumnSpan, HeaderWord};
use crate::compiler::tests::helpers::locations;
use crate::compiler::tests::test_types::{
    HeaderColumnsTestCase, HeaderWordTestCase, OutputColumnsTestCase,
};

const MODEL: &str = "MODEL (\n  columns (\n    order_id (type INTEGER),\n    amount (description 'x')\n  )\n);\n\
SELECT o.order_id, sum(amount) total, x AS \"Net\", \u{17f}um AS \u{17f}elect, count(*)\nFROM orders o\n";

#[test]
fn given_bare_header_words_when_reading_then_values_match_python_projection() {
    let test_cases = [
        HeaderWordTestCase {
            description: "true",
            word: "true",
            expected_value: HeaderWord::Bool(true),
        },
        HeaderWordTestCase {
            description: "null",
            word: "null",
            expected_value: HeaderWord::Null,
        },
        HeaderWordTestCase {
            description: "-007",
            word: "-007",
            expected_value: HeaderWord::Integer("-7".to_owned()),
        },
        HeaderWordTestCase {
            description: "\u{663}\u{664}",
            word: "\u{663}\u{664}",
            expected_value: HeaderWord::Integer("34".to_owned()),
        },
        HeaderWordTestCase {
            description: "1.",
            word: "1.",
            expected_value: HeaderWord::Float(1.0),
        },
        HeaderWordTestCase {
            description: "+.5",
            word: "+.5",
            expected_value: HeaderWord::Float(0.5),
        },
        HeaderWordTestCase {
            description: "1.2.3",
            word: "1.2.3",
            expected_value: HeaderWord::Text,
        },
        HeaderWordTestCase {
            description: "-",
            word: "-",
            expected_value: HeaderWord::Text,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            header_word_value(test_case.word),
            test_case.expected_value,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_model_files_when_locating_output_columns_then_simple_items_are_named() {
    let test_cases = [
        OutputColumnsTestCase {
            description: "qualified, implicit, quoted and long-s aliases",
            contents: MODEL,
            implicit_aliases: true,
            expected_columns: vec![
                ("order_id", [7, 8, 7, 18]),
                ("total", [7, 20, 7, 37]),
                ("Net", [7, 39, 7, 49]),
                ("\u{17f}elect", [7, 51, 7, 64]),
            ],
        },
        OutputColumnsTestCase {
            description: "implicit aliases can be left out",
            contents: MODEL,
            implicit_aliases: false,
            expected_columns: vec![
                ("order_id", [7, 8, 7, 18]),
                ("Net", [7, 39, 7, 49]),
                ("\u{17f}elect", [7, 51, 7, 64]),
            ],
        },
        OutputColumnsTestCase {
            description: "a top-level UNION has no single output list",
            contents: "MODEL (x 1);\nSELECT a FROM t UNION SELECT b FROM u\n",
            implicit_aliases: true,
            expected_columns: vec![],
        },
    ];

    for test_case in test_cases {
        let columns = model_output_columns(test_case.contents, test_case.implicit_aliases);

        assert_eq!(
            columns,
            locations(test_case.expected_columns),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_model_header_when_locating_columns_then_spans_and_locations_match_python() {
    let test_cases = [HeaderColumnsTestCase {
        description: "two columns with metadata",
        contents: MODEL,
        header_start: 7,
        header_end: 82,
        expected_body: (19, 80),
        expected_entries: vec![("order_id", [24, 47, 34, 46]), ("amount", [53, 77, 61, 76])],
        expected_locations: vec![("order_id", [3, 5, 3, 13]), ("amount", [4, 5, 4, 11])],
    }];

    for test_case in test_cases {
        let header: String = test_case
            .contents
            .chars()
            .skip(test_case.header_start)
            .take(test_case.header_end - test_case.header_start)
            .collect();

        let columns = model_header_columns(test_case.contents)
            .expect("tokenizes")
            .expect("declares columns");
        let named =
            model_header_column_locations(test_case.contents, &header, test_case.header_start)
                .expect("parses");

        assert_eq!(
            (columns.body_start, columns.body_end),
            test_case.expected_body,
            "{}",
            test_case.description
        );
        assert_eq!(
            columns.entries,
            test_case
                .expected_entries
                .into_iter()
                .map(
                    |(name, [entry_start, entry_end, metadata_start, metadata_end])| (
                        name.to_owned(),
                        HeaderColumnSpan {
                            entry_start,
                            entry_end,
                            metadata_start,
                            metadata_end
                        }
                    )
                )
                .collect::<Vec<_>>(),
            "{}",
            test_case.description
        );
        assert_eq!(
            named,
            locations(test_case.expected_locations),
            "{}",
            test_case.description
        );
    }
}
