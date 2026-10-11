use crate::name_patterns::main::compile_name_pattern::compile_name_pattern;
use crate::name_patterns::tests::test_types::NamePatternTestCase;

#[test]
fn given_name_patterns_when_matching_columns_then_whole_names_must_match() {
    let test_cases = [
        NamePatternTestCase {
            description: "an anchored pattern accepts a whole lowercase name",
            pattern: "^[a-z]+$",
            column_name: "books",
            expected_match: Ok(true),
        },
        NamePatternTestCase {
            description: "an unanchored pattern must still match the whole name",
            pattern: "amount_[0-9]+",
            column_name: "total_amount_12",
            expected_match: Ok(false),
        },
        NamePatternTestCase {
            description: "alternation is grouped before anchoring",
            pattern: "books|games",
            column_name: "games",
            expected_match: Ok(true),
        },
        NamePatternTestCase {
            description: "a trailing newline is not part of a whole-name match",
            pattern: "[a-z]+",
            column_name: "books\n",
            expected_match: Ok(false),
        },
        NamePatternTestCase {
            description: "an unclosed group is rejected",
            pattern: "(",
            column_name: "books",
            expected_match: Err("unclosed group"),
        },
        NamePatternTestCase {
            description: "look-around is rejected as unsupported",
            pattern: "(?=books)books",
            column_name: "books",
            expected_match: Err(
                "look-around, including look-ahead and look-behind, is not supported",
            ),
        },
    ];

    for test_case in test_cases {
        let matched = compile_name_pattern(test_case.pattern)
            .map(|pattern| pattern.matches(test_case.column_name));

        assert_eq!(
            matched,
            test_case.expected_match.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
