use crate::cost_allocation::_helpers::decimal::{add, divide, integer, multiply, text};
use crate::cost_allocation::tests::helpers::{decimal, float};
use crate::cost_allocation::tests::test_types::DecimalOperationTestCase;

#[test]
fn given_python_decimals_when_operating_then_rounds_like_the_default_context() {
    let test_cases = [
        DecimalOperationTestCase {
            description: "inexact division rounds to 28 digits",
            result: divide(&decimal("1.0"), 3),
            expected_text: "0.3333333333333333333333333333",
        },
        DecimalOperationTestCase {
            description: "tiny quotients switch to scientific text",
            result: divide(&decimal("0.000005"), 7),
            expected_text: "7.142857142857142857142857143E-7",
        },
        DecimalOperationTestCase {
            description: "exact division keeps the ideal exponent",
            result: divide(&decimal("12"), 4),
            expected_text: "3",
        },
        DecimalOperationTestCase {
            description: "exact division keeps needed fraction digits",
            result: divide(&decimal("7.5"), 3),
            expected_text: "2.5",
        },
        DecimalOperationTestCase {
            description: "zero division keeps the dividend exponent",
            result: divide(&decimal("0.000000"), 3_600),
            expected_text: "0.000000",
        },
        DecimalOperationTestCase {
            description: "adding zero aligns a large exponent and rounds",
            result: add(&decimal("1E+30"), &integer(0)),
            expected_text: "1.000000000000000000000000000E+30",
        },
        DecimalOperationTestCase {
            description: "a half above an odd coefficient rounds up with carry",
            result: add(&decimal("9999999999999999999999999999"), &decimal("0.5")),
            expected_text: "1.000000000000000000000000000E+28",
        },
        DecimalOperationTestCase {
            description: "a half above an even coefficient rounds to even",
            result: add(&decimal("9999999999999999999999999998"), &decimal("0.5")),
            expected_text: "9999999999999999999999999998",
        },
        DecimalOperationTestCase {
            description: "long products round to 28 digits",
            result: multiply(
                &decimal("3.123456789012345678901234567890123"),
                &decimal("1.234"),
            ),
            expected_text: "3.854345677641234567764123457",
        },
        DecimalOperationTestCase {
            description: "zero products keep the summed exponent",
            result: multiply(&integer(0), &decimal("3.00")),
            expected_text: "0.00",
        },
        DecimalOperationTestCase {
            description: "integral floats keep repr's trailing zero",
            result: float(3_600.0),
            expected_text: "3600.0",
        },
        DecimalOperationTestCase {
            description: "small floats read repr's exponent form",
            result: float(5e-6),
            expected_text: "0.000005",
        },
        DecimalOperationTestCase {
            description: "large floats read repr's exponent form",
            result: float(1e16),
            expected_text: "1E+16",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            text(&test_case.result),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
