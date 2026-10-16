use crate::dbt_profile::main::dbt_bool_text::dbt_bool_text;
use crate::dbt_profile::main::dbt_number_text::dbt_number_text;
use crate::dbt_profile::models::DbtNumberParse;
use crate::dbt_profile::tests::test_types::{DbtBoolTestCase, DbtNumberTestCase};

#[test]
fn given_profile_text_when_coercing_to_bool_then_dbt_spellings_are_read() {
    let test_cases = [
        DbtBoolTestCase {
            description: "padded mixed-case yes",
            text: " Yes ",
            expected_bool: Some(true),
        },
        DbtBoolTestCase {
            description: "uppercase on",
            text: "ON",
            expected_bool: Some(true),
        },
        DbtBoolTestCase {
            description: "whitespace-padded no",
            text: "\tno\n",
            expected_bool: Some(false),
        },
        DbtBoolTestCase {
            description: "zero",
            text: "0",
            expected_bool: Some(false),
        },
        DbtBoolTestCase {
            description: "other digit",
            text: "2",
            expected_bool: None,
        },
        DbtBoolTestCase {
            description: "empty",
            text: "",
            expected_bool: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            dbt_bool_text(test_case.text),
            test_case.expected_bool,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_profile_text_when_coercing_to_number_then_decimal_separator_selects_float() {
    let test_cases = [
        DbtNumberTestCase {
            description: "padded negative integer",
            text: " -3 ",
            expected_parse: ("-3", DbtNumberParse::Integer),
        },
        DbtNumberTestCase {
            description: "decimal",
            text: "1.5",
            expected_parse: ("1.5", DbtNumberParse::Float),
        },
        DbtNumberTestCase {
            description: "exponent without separator parses as integer",
            text: "1e3",
            expected_parse: ("1e3", DbtNumberParse::Integer),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            dbt_number_text(test_case.text),
            test_case.expected_parse,
            "{}",
            test_case.description
        );
    }
}
