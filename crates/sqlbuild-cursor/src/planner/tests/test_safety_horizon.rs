use crate::algebra::models::{CivilDate, DurationSpan, Grain, Scalar, ScalarValue};
use crate::planner::main::safety_horizon::safety_horizon;
use crate::planner::tests::helpers::timestamp;
use crate::planner::tests::test_types::HorizonTestCase;

#[test]
fn given_invocation_clock_when_resolving_horizon_then_calendar_and_grain_are_preserved() {
    let test_cases = [
        HorizonTestCase {
            description: "calendar month clamps day",
            months: 1,
            grain: Grain::Hour,
            date_only: false,
            expected_horizon: timestamp(2, 28, 12, 0),
        },
        HorizonTestCase {
            description: "date retains final day",
            months: 1,
            grain: Grain::Day,
            date_only: true,
            expected_horizon: Scalar {
                handle: None,
                value: ScalarValue::Date(CivilDate {
                    year: 2026,
                    month: 2,
                    day: 28,
                }),
            },
        },
        HorizonTestCase {
            description: "month grain floors shifted clock",
            months: 1,
            grain: Grain::Month,
            date_only: false,
            expected_horizon: timestamp(2, 1, 0, 0),
        },
        HorizonTestCase {
            description: "zero duration retains current partition",
            months: 0,
            grain: Grain::Day,
            date_only: false,
            expected_horizon: timestamp(1, 31, 0, 0),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            safety_horizon(
                &timestamp(1, 31, 12, 30),
                &DurationSpan {
                    months: test_case.months,
                    days: 0,
                    hours: 0,
                    minutes: 0,
                    seconds: 0
                },
                test_case.grain,
                test_case.date_only
            ),
            Ok(test_case.expected_horizon),
            "{}",
            test_case.description,
        );
    }
}
