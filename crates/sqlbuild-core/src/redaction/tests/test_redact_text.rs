use crate::redaction::main::redact_text::redact_text;
use crate::redaction::tests::test_types::RedactTestCase;

#[test]
fn given_diagnostic_text_when_redacting_then_matches_python_substitutions() {
    let test_cases = [
        RedactTestCase {
            description: "authorization header keeps its scheme separator",
            text: "Authorization: Bearer abc.def",
            expected_text: "Authorization: [REDACTED]",
        },
        RedactTestCase {
            description: "named secrets and URI passwords",
            text: "password = 'hunter2', url=postgres://user:pw@host/db",
            expected_text: "password = [REDACTED], url=postgres://user:[REDACTED]@host/db",
        },
        RedactTestCase {
            description: "plain text is unchanged",
            text: "nothing to see",
            expected_text: "nothing to see",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            redact_text(test_case.text),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
