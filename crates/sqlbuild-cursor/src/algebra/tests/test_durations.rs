use crate::algebra::errors::CursorError;
use crate::algebra::main::parse_duration::parse_duration;
use crate::algebra::main::shift_by_duration::shift_by_duration;
use crate::algebra::models::{DurationSpan, Moment};
use crate::algebra::tests::helpers::{civil, local};
use crate::algebra::tests::test_types::{DurationTestCase, ShiftTestCase};

const NO_SPAN: DurationSpan = DurationSpan {
    months: 0,
    days: 0,
    hours: 0,
    minutes: 0,
    seconds: 0,
};

#[test]
fn given_duration_text_when_parsing_then_matches_the_python_pattern() {
    let test_cases = [
        DurationTestCase {
            description: "every unit in order",
            text: "1y2mo3d4h5m6s",
            expected_digits: Some(["1", "2", "3", "4", "5", "6"]),
        },
        DurationTestCase {
            description: "a trailing newline and Unicode digits",
            text: "\u{0663}d\n",
            expected_digits: Some(["0", "0", "3", "0", "0", "0"]),
        },
        DurationTestCase {
            description: "units out of order",
            text: "1mo1y",
            expected_digits: None,
        },
        DurationTestCase {
            description: "a zero duration",
            text: "0y0mo",
            expected_digits: None,
        },
    ];

    for test_case in test_cases {
        let digits = parse_duration(test_case.text).map(|digits| {
            [
                digits.years,
                digits.months,
                digits.days,
                digits.hours,
                digits.minutes,
                digits.seconds,
            ]
        });

        assert_eq!(
            digits,
            test_case
                .expected_digits
                .map(|parts| parts.map(str::to_owned)),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_moment_when_shifting_by_duration_then_matches_python() {
    let test_cases = [
        ShiftTestCase {
            description: "month end clamps to a leap February",
            moment: Moment::Timestamp {
                local: local(civil(2024, 1, 31), (12, 0, 0, 0)),
                fold: true,
            },
            span: DurationSpan {
                months: 1,
                ..NO_SPAN
            },
            direction: 1,
            expected_moment: Ok(Moment::Timestamp {
                local: local(civil(2024, 2, 29), (12, 0, 0, 0)),
                fold: false,
            }),
        },
        ShiftTestCase {
            description: "a date only moves by whole days",
            moment: Moment::Date(civil(2024, 3, 1)),
            span: DurationSpan {
                hours: 36,
                ..NO_SPAN
            },
            direction: -1,
            expected_moment: Ok(Moment::Date(civil(2024, 2, 29))),
        },
        ShiftTestCase {
            description: "a timedelta beyond its day limit",
            moment: Moment::Date(civil(2024, 3, 1)),
            span: DurationSpan {
                days: 1_000_000_000,
                ..NO_SPAN
            },
            direction: 1,
            expected_moment: Err(CursorError::Overflow(
                "days=1000000000; must have magnitude <= 999999999".to_owned(),
            )),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            shift_by_duration(test_case.moment, &test_case.span, test_case.direction),
            test_case.expected_moment,
            "{}",
            test_case.description
        );
    }
}
