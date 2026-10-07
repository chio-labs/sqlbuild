use crate::digest::main::content_digest::content_digest;
use crate::digest::main::hex_digest::hex_digest;
use crate::digest::tests::test_types::{ContentDigestTestCase, HexDigestTestCase};

#[test]
fn given_parts_when_digesting_then_only_identical_parts_match() {
    let test_cases = [
        ContentDigestTestCase {
            description: "identical parts",
            left: &["cents", "@cents(amount)"],
            right: &["cents", "@cents(amount)"],
            expected_equal: true,
        },
        ContentDigestTestCase {
            description: "a boundary moved between parts",
            left: &["cents", "@cents(amount)"],
            right: &["cents@", "cents(amount)"],
            expected_equal: false,
        },
        ContentDigestTestCase {
            description: "an empty part added",
            left: &["cents"],
            right: &["cents", ""],
            expected_equal: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            content_digest(test_case.left) == content_digest(test_case.right),
            test_case.expected_equal,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_digest_when_formatting_then_text_is_lowercase_hexadecimal() {
    let test_cases = [
        HexDigestTestCase {
            description: "one part",
            parts: &["orders"],
            expected_length: 64,
        },
        HexDigestTestCase {
            description: "no parts",
            parts: &[],
            expected_length: 64,
        },
    ];

    for test_case in test_cases {
        let text = hex_digest(&content_digest(test_case.parts));

        assert_eq!(
            text.len(),
            test_case.expected_length,
            "{}",
            test_case.description
        );
        assert!(
            text.chars()
                .all(|character| matches!(character, '0'..='9' | 'a'..='f')),
            "{}",
            test_case.description
        );
    }
}
