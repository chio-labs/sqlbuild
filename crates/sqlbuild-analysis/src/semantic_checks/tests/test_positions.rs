use crate::semantic_checks::_helpers::metadata_checks::positions::text_position;
use crate::semantic_checks::tests::test_types::TextPositionTestCase;

#[test]
fn given_names_in_text_when_locating_then_matches_python_whole_word_positions() {
    let test_cases = [
        TextPositionTestCase {
            description: "a longer word sharing the prefix is skipped",
            text: "SELECT amount_total, amount\nFROM t",
            name: "amount",
            offset: 0,
            expected_position: Ok((1, 22)),
        },
        TextPositionTestCase {
            description: "a later line",
            text: "x\ny amount",
            name: "amount",
            offset: 0,
            expected_position: Ok((2, 3)),
        },
        TextPositionTestCase {
            description: "an absent name points at the offset",
            text: "abc",
            name: "zzz",
            offset: 0,
            expected_position: Ok((1, 1)),
        },
        TextPositionTestCase {
            description: "the search starts at the offset",
            text: "a amount\n-- amount",
            name: "amount",
            offset: 3,
            expected_position: Ok((2, 4)),
        },
        TextPositionTestCase {
            description: "columns count code points after non-ASCII text",
            text: "caf\u{e9} amount",
            name: "amount",
            offset: 0,
            expected_position: Ok((1, 6)),
        },
        TextPositionTestCase {
            description: "an empty name in empty text",
            text: "",
            name: "",
            offset: 0,
            expected_position: Ok((1, 1)),
        },
        TextPositionTestCase {
            description: "a non-ASCII letter before the name is part of the word",
            text: "\u{e9}amount amount",
            name: "amount",
            offset: 0,
            expected_position: Ok((1, 9)),
        },
        TextPositionTestCase {
            description: "a non-ASCII digit joins the word and a line separator is no newline",
            text: "a\u{2028}b \u{663}amount amount",
            name: "amount",
            offset: 0,
            expected_position: Ok((1, 13)),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            text_position(test_case.text, test_case.name, test_case.offset),
            test_case.expected_position,
            "{}",
            test_case.description
        );
    }
}
