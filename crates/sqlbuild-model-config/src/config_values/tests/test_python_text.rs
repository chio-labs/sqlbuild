use crate::config_values::models::ConfigNode;
use crate::config_values::tests::helpers::{host_text, text};
use crate::config_values::tests::test_types::PythonTextTestCase;
use crate::types::AuthoredNode;

#[test]
fn given_config_values_when_printed_then_scalars_print_natively_and_the_rest_by_python() {
    let test_cases = [
        PythonTextTestCase {
            description: "plain scalars print as Python literals",
            value: ConfigNode::Float(1e16),
            expected_str: "1e+16",
            expected_repr: "1e+16",
        },
        PythonTextTestCase {
            description: "a boolean and None print as Python spells them",
            value: ConfigNode::Bool(false),
            expected_str: "False",
            expected_repr: "False",
        },
        PythonTextTestCase {
            description: "a string prints itself; its repr is Python's",
            value: text("it's\u{200b}"),
            expected_str: "it's\u{200b}",
            expected_repr: "<repr>0",
        },
        PythonTextTestCase {
            description: "a container prints by Python, never approximated in Rust",
            value: ConfigNode::List(vec![host_text("warn"), text("x")]),
            expected_str: "<str>0",
            expected_repr: "<repr>0",
        },
        PythonTextTestCase {
            description: "a host value prints by Python",
            value: host_text("warn"),
            expected_str: "<str>1",
            expected_repr: "<repr>1",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            (test_case.value.python_str(), test_case.value.python_repr()),
            (
                test_case.expected_str.to_owned(),
                test_case.expected_repr.to_owned()
            ),
            "{}",
            test_case.description
        );
    }
}
