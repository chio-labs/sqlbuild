use crate::config_values::models::ConfigNode;
use crate::config_values::tests::helpers::{host_text, text};
use crate::config_values::tests::test_types::PythonTextTestCase;
use crate::types::AuthoredNode;

#[test]
fn given_config_values_when_printed_then_str_and_repr_match_python() {
    let test_cases = [
        PythonTextTestCase {
            description: "scalars print as Python literals",
            value: ConfigNode::Tuple(vec![
                ConfigNode::Null,
                ConfigNode::Bool(true),
                ConfigNode::Int(-3),
                ConfigNode::Float(1e16),
            ]),
            expected_str: "(None, True, -3, 1e+16)",
            expected_repr: "(None, True, -3, 1e+16)",
        },
        PythonTextTestCase {
            description: "a string prints itself and reprs quoted",
            value: text("it's"),
            expected_str: "it's",
            expected_repr: "\"it's\"",
        },
        PythonTextTestCase {
            description: "a one-item tuple keeps its comma",
            value: ConfigNode::Tuple(vec![ConfigNode::Float(1.0)]),
            expected_str: "(1.0,)",
            expected_repr: "(1.0,)",
        },
        PythonTextTestCase {
            description: "mappings and lists nest item reprs, host values their own",
            value: ConfigNode::Map(vec![(
                text("severity"),
                ConfigNode::List(vec![host_text("warn"), text("x")]),
            )]),
            expected_str: "{'severity': [<Severity.WARN: 'warn'>, 'x']}",
            expected_repr: "{'severity': [<Severity.WARN: 'warn'>, 'x']}",
        },
        PythonTextTestCase {
            description: "a host value prints its own str",
            value: host_text("warn"),
            expected_str: "warn",
            expected_repr: "<Severity.WARN: 'warn'>",
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
