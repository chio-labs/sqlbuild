use crate::type_system::_helpers::python_text::{PythonInt, python_int, split_type_and_params};
use crate::type_system::tests::test_types::{PythonIntTestCase, SplitTypeTestCase};

#[test]
fn given_parameter_text_when_parsing_as_python_int_then_python_result_is_returned() {
    let test_cases = [
        PythonIntTestCase {
            description: "padded digits",
            text: " \t42\x1c",
            expected_value: PythonInt::Value(42),
        },
        PythonIntTestCase {
            description: "signs",
            text: "-7",
            expected_value: PythonInt::Value(-7),
        },
        PythonIntTestCase {
            description: "single underscores between digits",
            text: "+1_000",
            expected_value: PythonInt::Value(1000),
        },
        PythonIntTestCase {
            description: "double underscores",
            text: "1__0",
            expected_value: PythonInt::Invalid,
        },
        PythonIntTestCase {
            description: "leading underscore",
            text: "_1",
            expected_value: PythonInt::Invalid,
        },
        PythonIntTestCase {
            description: "words",
            text: "MAX",
            expected_value: PythonInt::Invalid,
        },
        PythonIntTestCase {
            description: "the smallest i64",
            text: "-9223372036854775808",
            expected_value: PythonInt::Value(i64::MIN),
        },
        PythonIntTestCase {
            description: "beyond i64",
            text: "9223372036854775808",
            expected_value: PythonInt::TooLarge,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            python_int(test_case.text),
            test_case.expected_value,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_type_text_when_splitting_then_python_name_and_parameters_are_returned() {
    let test_cases = [
        SplitTypeTestCase {
            description: "name only",
            type_sql: "VARCHAR",
            expected_split: Some(("VARCHAR", vec![])),
        },
        SplitTypeTestCase {
            description: "parameters skip what int() rejects",
            type_sql: "DECIMAL(10,X,2)",
            expected_split: Some(("DECIMAL", vec![10, 2])),
        },
        SplitTypeTestCase {
            description: "a final newline is allowed by the regex end anchor",
            type_sql: "NUMBER(5)\n",
            expected_split: Some(("NUMBER", vec![5])),
        },
        SplitTypeTestCase {
            description: "anything else keeps the whole text",
            type_sql: "ARRAY<INT>",
            expected_split: Some(("ARRAY<INT>", vec![])),
        },
        SplitTypeTestCase {
            description: "nested parentheses keep the whole text",
            type_sql: "A(1)(2)",
            expected_split: Some(("A(1)(2)", vec![])),
        },
        SplitTypeTestCase {
            description: "a parameter beyond i64 defers",
            type_sql: "A(99999999999999999999)",
            expected_split: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            split_type_and_params(test_case.type_sql),
            test_case.expected_split,
            "{}",
            test_case.description
        );
    }
}
