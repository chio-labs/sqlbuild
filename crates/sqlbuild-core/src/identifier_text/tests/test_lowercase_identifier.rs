use crate::identifier_text::main::is_lowercase_identifier::is_lowercase_identifier;
use crate::identifier_text::tests::test_types::LowercaseIdentifierTestCase;

#[test]
fn given_names_when_checked_then_only_lowercase_ascii_identifiers_pass() {
    let test_cases = [
        LowercaseIdentifierTestCase {
            description: "a plain name",
            value: "orders",
            expected_valid: true,
        },
        LowercaseIdentifierTestCase {
            description: "one letter",
            value: "a",
            expected_valid: true,
        },
        LowercaseIdentifierTestCase {
            description: "digits and underscores",
            value: "a1_b",
            expected_valid: true,
        },
        LowercaseIdentifierTestCase {
            description: "a trailing underscore",
            value: "abc_",
            expected_valid: true,
        },
        LowercaseIdentifierTestCase {
            description: "an empty name",
            value: "",
            expected_valid: false,
        },
        LowercaseIdentifierTestCase {
            description: "an uppercase letter",
            value: "A",
            expected_valid: false,
        },
        LowercaseIdentifierTestCase {
            description: "a leading digit",
            value: "1a",
            expected_valid: false,
        },
        LowercaseIdentifierTestCase {
            description: "a leading underscore",
            value: "_a",
            expected_valid: false,
        },
        LowercaseIdentifierTestCase {
            description: "a hyphen",
            value: "a-b",
            expected_valid: false,
        },
        LowercaseIdentifierTestCase {
            description: "a trailing newline",
            value: "ab\n",
            expected_valid: false,
        },
        LowercaseIdentifierTestCase {
            description: "an accented letter",
            value: "\u{e9}",
            expected_valid: false,
        },
        LowercaseIdentifierTestCase {
            description: "a dotless i",
            value: "a\u{131}",
            expected_valid: false,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            is_lowercase_identifier(test_case.value),
            test_case.expected_valid,
            "{}",
            test_case.description
        );
    }
}
