use crate::toml::main::toml_literal::toml_literal;
use crate::toml::models::TomlLiteral;
use crate::toml::tests::test_types::TomlLiteralTestCase;

#[test]
fn given_literals_when_written_then_toml_text_matches_the_rule_harness_encoding() {
    let test_cases = [
        TomlLiteralTestCase {
            description: "a boolean",
            value: TomlLiteral::Bool(true),
            expected_text: "true",
        },
        TomlLiteralTestCase {
            description: "an integer keeps its digits",
            value: TomlLiteral::Integer("-5".to_owned()),
            expected_text: "-5",
        },
        TomlLiteralTestCase {
            description: "a plain string",
            value: TomlLiteral::Text("plain".to_owned()),
            expected_text: "\"plain\"",
        },
        TomlLiteralTestCase {
            description: "quotes and backslashes are escaped",
            value: TomlLiteral::Text("a\"b\\c".to_owned()),
            expected_text: "\"a\\\"b\\\\c\"",
        },
        TomlLiteralTestCase {
            description: "an empty array",
            value: TomlLiteral::Array(Vec::new()),
            expected_text: "[]",
        },
        TomlLiteralTestCase {
            description: "nested arrays",
            value: TomlLiteral::Array(vec![
                TomlLiteral::Integer("1".to_owned()),
                TomlLiteral::Array(vec![TomlLiteral::Bool(false)]),
            ]),
            expected_text: "[1, [false]]",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            toml_literal(&test_case.value),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
