use crate::config_values::main::config_entry::config_entry;
use crate::config_values::models::ConfigNode;
use crate::config_values::tests::helpers::{host_text, text};
use crate::config_values::tests::test_types::ConfigEntryTestCase;

#[test]
fn given_config_entries_when_read_by_string_key_then_python_dict_equality_applies() {
    let test_cases = [
        ConfigEntryTestCase {
            description: "a string key is found",
            entries: vec![(text("schema"), text("analytics"))],
            key: "schema",
            expected_value: Some(text("analytics")),
        },
        ConfigEntryTestCase {
            description: "a str-enum key equals its text",
            entries: vec![(host_text("schema"), ConfigNode::Int(1))],
            key: "schema",
            expected_value: Some(ConfigNode::Int(1)),
        },
        ConfigEntryTestCase {
            description: "a number key never equals a string",
            entries: vec![(ConfigNode::Int(1), text("one"))],
            key: "1",
            expected_value: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            config_entry(&test_case.entries, test_case.key).cloned(),
            test_case.expected_value,
            "{}",
            test_case.description
        );
    }
}
