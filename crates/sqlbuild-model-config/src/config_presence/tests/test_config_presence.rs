use crate::config_presence::_helpers::macro_calls::macro_call;
use crate::config_presence::_helpers::scan::scan;
use crate::config_presence::main::blocks_config_reuse::blocks_config_reuse;
use crate::config_presence::main::contains_template::contains_template;
use crate::config_presence::main::entry_macro_path::entry_macro_path;
use crate::config_presence::main::mutable_config_value::mutable_config_value;
use crate::config_presence::models::MacroPath;
use crate::config_presence::tests::test_types::{
    EntryMacroPathTestCase, PresenceTestCase, ReuseTestCase,
};
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
                    Value::Tuple(vec![Value::Str("@py.cents (amount)")]),
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
            description: "a tab and an ideographic space before the call",
            value: Value::Str("@m\u{3000}\t("),
            expected_template: false,
            expected_macro_call: true,
        },
        PresenceTestCase {
            description: "Unicode whitespace after a macro name",
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
            value: Value::List(vec![Value::Str("@m\u{2003}("), Value::Str("@py.n(")]),
            expected_template: false,
            expected_macro_call: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                contains_template(&test_case.value),
                scan(&test_case.value, &macro_call)
            ),
            (test_case.expected_template, test_case.expected_macro_call),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_config_values_when_checking_reuse_then_python_answers_are_returned() {
    let test_cases = [
        ReuseTestCase {
            description: "plain scalars neither block reuse nor are mutable",
            value: Value::Tuple(vec![
                Value::Int(1),
                Value::Bool(true),
                Value::Null,
                Value::Float,
            ]),
            expected_blocks_reuse: false,
            expected_mutable: false,
        },
        ReuseTestCase {
            description: "a plain string is reusable",
            value: Value::Str("Orders by customer."),
            expected_blocks_reuse: false,
            expected_mutable: false,
        },
        ReuseTestCase {
            description: "a template blocks reuse",
            value: Value::Str("${var.label}"),
            expected_blocks_reuse: true,
            expected_mutable: false,
        },
        ReuseTestCase {
            description: "a macro call blocks reuse",
            value: Value::Str("@py.label ()"),
            expected_blocks_reuse: true,
            expected_mutable: false,
        },
        ReuseTestCase {
            description: "a non-string mapping key blocks reuse and a mapping is mutable",
            value: Value::Map(vec![(Value::Int(1), Value::Str("orders"))]),
            expected_blocks_reuse: true,
            expected_mutable: true,
        },
        ReuseTestCase {
            description: "an unsupported object blocks reuse and is mutable",
            value: Value::Tuple(vec![Value::Date("2024-01-01")]),
            expected_blocks_reuse: true,
            expected_mutable: true,
        },
        ReuseTestCase {
            description: "a list of plain strings is reusable metadata but mutable",
            value: Value::List(vec![Value::Str("orders")]),
            expected_blocks_reuse: false,
            expected_mutable: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                blocks_config_reuse(&test_case.value),
                mutable_config_value(&test_case.value)
            ),
            (test_case.expected_blocks_reuse, test_case.expected_mutable),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_config_entries_when_walking_for_macros_then_the_first_path_matches_python() {
    let test_cases = [
        EntryMacroPathTestCase {
            description: "a plain scalar holds no macro",
            key: Value::Str("materialized"),
            value: Value::Str("table"),
            expected_path: MacroPath::Absent,
        },
        EntryMacroPathTestCase {
            description: "a nested mapping names every key down to the string",
            key: Value::Str("columns"),
            value: Value::Map(vec![(
                Value::Str("id"),
                Value::Map(vec![
                    (Value::Str("type"), Value::Str("INTEGER")),
                    (Value::Str("description"), Value::Str("@py.cents(id)")),
                ]),
            )]),
            expected_path: MacroPath::Found(vec![
                "columns".to_owned(),
                "id".to_owned(),
                "description".to_owned(),
            ]),
        },
        EntryMacroPathTestCase {
            description: "list items report the path of the list",
            key: Value::Str("tags"),
            value: Value::List(vec![Value::Str("daily"), Value::Str("@py.later()")]),
            expected_path: MacroPath::Found(vec!["tags".to_owned()]),
        },
        EntryMacroPathTestCase {
            description: "a mapping key that is not a string is skipped",
            key: Value::Str("config"),
            value: Value::Map(vec![(Value::Int(1), Value::Str("@py.skipped()"))]),
            expected_path: MacroPath::Absent,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            entry_macro_path(&test_case.key, &test_case.value),
            test_case.expected_path,
            "{}",
            test_case.description
        );
    }
}
