use crate::config_values::main::checked_cursor_bound::checked_cursor_bound;
use crate::config_values::main::checked_flag::checked_flag;
use crate::config_values::main::checked_integer::checked_integer;
use crate::config_values::main::checked_text::checked_text;
use crate::config_values::main::checked_texts::checked_texts;
use crate::config_values::models::ConfigNode;
use crate::config_values::tests::helpers::{
    cursor_outcome, host_date, host_text, outcome, text, texts,
};
use crate::config_values::tests::test_types::CheckedReadTestCase;

#[test]
fn given_config_values_when_read_as_typed_values_then_types_are_checked_as_python_does() {
    let test_cases = [
        CheckedReadTestCase {
            description: "an absent or null value reads as none",
            value: Some(ConfigNode::Null),
            expected_text: "none",
            expected_flag: "none",
            expected_integer: "none",
            expected_texts: "none",
            expected_cursor_bound: "none",
        },
        CheckedReadTestCase {
            description: "a present empty string is a string",
            value: Some(text("")),
            expected_text: "value",
            expected_flag: "a boolean",
            expected_integer: "an integer",
            expected_texts: "a list or tuple of strings",
            expected_cursor_bound: "stringified",
        },
        CheckedReadTestCase {
            description: "a str-enum member is a string",
            value: Some(host_text("daily")),
            expected_text: "value",
            expected_flag: "a boolean",
            expected_integer: "an integer",
            expected_texts: "a list or tuple of strings",
            expected_cursor_bound: "stringified",
        },
        CheckedReadTestCase {
            description: "a boolean is not an integer or a cursor bound",
            value: Some(ConfigNode::Bool(true)),
            expected_text: "a string",
            expected_flag: "value",
            expected_integer: "an integer",
            expected_texts: "a list or tuple of strings",
            expected_cursor_bound: "a string, integer, date, or datetime",
        },
        CheckedReadTestCase {
            description: "an integer reads as an integer and a stringified bound",
            value: Some(ConfigNode::Int(-4)),
            expected_text: "a string",
            expected_flag: "a boolean",
            expected_integer: "value",
            expected_texts: "a list or tuple of strings",
            expected_cursor_bound: "stringified",
        },
        CheckedReadTestCase {
            description: "a date is a dated cursor bound only",
            value: Some(host_date()),
            expected_text: "a string",
            expected_flag: "a boolean",
            expected_integer: "an integer",
            expected_texts: "a list or tuple of strings",
            expected_cursor_bound: "dated",
        },
        CheckedReadTestCase {
            description: "a tuple of strings is a string sequence",
            value: Some(ConfigNode::Tuple(vec![text("a"), host_text("b")])),
            expected_text: "a string",
            expected_flag: "a boolean",
            expected_integer: "an integer",
            expected_texts: "value",
            expected_cursor_bound: "a string, integer, date, or datetime",
        },
        CheckedReadTestCase {
            description: "a list holding a non-string is not a string sequence",
            value: Some(ConfigNode::List(vec![text("a"), ConfigNode::Int(1)])),
            expected_text: "a string",
            expected_flag: "a boolean",
            expected_integer: "an integer",
            expected_texts: "a list or tuple of strings",
            expected_cursor_bound: "a string, integer, date, or datetime",
        },
        CheckedReadTestCase {
            description: "a list of strings is a string sequence",
            value: Some(texts(&["a"])),
            expected_text: "a string",
            expected_flag: "a boolean",
            expected_integer: "an integer",
            expected_texts: "value",
            expected_cursor_bound: "a string, integer, date, or datetime",
        },
    ];
    for test_case in test_cases {
        let value = test_case.value.as_ref();
        assert_eq!(
            [
                outcome(checked_text("key", value)),
                outcome(checked_flag("key", value)),
                outcome(checked_integer("key", value)),
                outcome(checked_texts("key", value)),
                cursor_outcome(checked_cursor_bound("key", value)),
            ],
            [
                test_case.expected_text,
                test_case.expected_flag,
                test_case.expected_integer,
                test_case.expected_texts,
                test_case.expected_cursor_bound,
            ],
            "{}",
            test_case.description
        );
    }
}
