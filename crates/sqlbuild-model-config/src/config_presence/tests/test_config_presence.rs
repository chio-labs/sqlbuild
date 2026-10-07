use crate::config_presence::main::contains_macro_call::contains_macro_call;
use crate::config_presence::main::contains_template::contains_template;
use crate::config_presence::models::Presence;
use crate::config_presence::tests::test_types::PresenceTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_config_values_when_scanning_then_presence_matches_python_or_defers() {
    let test_cases = [
        PresenceTestCase {
            description: "plain scalars contain nothing",
            value: Value::List(vec![
                Value::Int(1),
                Value::Bool(true),
                Value::Null,
                Value::Float,
            ]),
            expected_template: Presence::Absent,
            expected_macro_call: Presence::Absent,
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
            expected_template: Presence::Absent,
            expected_macro_call: Presence::Present,
        },
        PresenceTestCase {
            description: "a template token anywhere in a string",
            value: Value::Str("prefix_${target.schema}"),
            expected_template: Presence::Present,
            expected_macro_call: Presence::Absent,
        },
        PresenceTestCase {
            description: "an at-name without a call or with an invalid start is no macro",
            value: Value::Str("mail@example.com @1x( @ (x)"),
            expected_template: Presence::Absent,
            expected_macro_call: Presence::Absent,
        },
        PresenceTestCase {
            description: "Python separators count as whitespace before the call",
            value: Value::Str("@m\u{1f}\t("),
            expected_template: Presence::Absent,
            expected_macro_call: Presence::Present,
        },
        PresenceTestCase {
            description: "non-ASCII after a macro name defers to Python's whitespace class",
            value: Value::Str("@m\u{a0}("),
            expected_template: Presence::Absent,
            expected_macro_call: Presence::Deferred,
        },
        PresenceTestCase {
            description: "a later call outweighs an earlier deferral",
            value: Value::List(vec![Value::Str("@m\u{2003}("), Value::Str("@n(")]),
            expected_template: Presence::Absent,
            expected_macro_call: Presence::Present,
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
