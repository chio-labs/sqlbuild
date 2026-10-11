use crate::replay::_helpers::console::tenths_of_seconds;
use crate::replay::tests::test_types::TenthsTestCase;

#[test]
fn given_elapsed_milliseconds_when_formatting_seconds_then_matches_python_rounding() {
    let test_cases = [
        TenthsTestCase {
            description: "exact binary tie rounds to even",
            milliseconds: 250,
            expected_text: "0.2",
        },
        TenthsTestCase {
            description: "inexact half rounds on the binary value",
            milliseconds: 350,
            expected_text: "0.3",
        },
        TenthsTestCase {
            description: "upper exact tie rounds to even",
            milliseconds: 750,
            expected_text: "0.8",
        },
        TenthsTestCase {
            description: "seconds above one",
            milliseconds: 2_450,
            expected_text: "2.5",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            tenths_of_seconds(test_case.milliseconds),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
