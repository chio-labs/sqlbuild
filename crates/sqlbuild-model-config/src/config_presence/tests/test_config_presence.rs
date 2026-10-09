use crate::config_presence::main::contains_macro_call::contains_macro_call;
use crate::config_presence::main::contains_template::contains_template;
use crate::config_presence::tests::test_types::PresenceTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_config_values_when_scanning_then_presence_matches_python() {
    let test_cases = [
        PresenceTestCase {
            description: "plain scalars contain nothing",
            value: Value::List(vec![
                Value::Int(1),
                Value::Bool(true),
                Value::Null,
                Value::Float,
            ]),
            expected_template: false,
            expected_macro_call: false,
        },
        PresenceTestCase {
            description: "nested mapping values are scanned, keys are not",
            value: Value::Map(vec![
                (Value::Str("${key}"), Value::Str("plain")),
                (
                    Value::Str("columns"),
                    Value::Tuple(vec![Value::Str("@cents (amount)")]),
                ),
            ]),
            expected_template: false,
            expected_macro_call: true,
        },
        PresenceTestCase {
            description: "a template token anywhere in a string",
            value: Value::Str("prefix_${target.schema}"),
            expected_template: true,
            expected_macro_call: false,
        },
        PresenceTestCase {
            description: "an at-name without a call or with an invalid start is no macro",
            value: Value::Str("mail@example.com @1x( @ (x)"),
            expected_template: false,
            expected_macro_call: false,
        },
        PresenceTestCase {
            description: "Python separators count as whitespace before the call",
            value: Value::Str("@m\u{1f}\t("),
            expected_template: false,
            expected_macro_call: true,
        },
        PresenceTestCase {
            description: "Unicode whitespace after a macro name counts as Python's \\s",
            value: Value::Str("@m\u{a0}\u{3000}("),
            expected_template: false,
            expected_macro_call: true,
        },
        PresenceTestCase {
            description: "other non-ASCII after a macro name is no call",
            value: Value::Str("@m\u{e9}( @n\u{200b}("),
            expected_template: false,
            expected_macro_call: false,
        },
        PresenceTestCase {
            description: "a later call is found after Unicode whitespace that is no call",
            value: Value::List(vec![Value::Str("@m\u{2003}("), Value::Str("@n(")]),
            expected_template: false,
            expected_macro_call: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                contains_template(&test_case.value),
                contains_macro_call(&test_case.value)
            ),
            (test_case.expected_template, test_case.expected_macro_call),
            "{}",
            test_case.description
        );
    }
}
