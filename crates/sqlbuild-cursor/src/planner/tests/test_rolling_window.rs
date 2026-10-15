use crate::algebra::models::Grain;
use crate::planner::main::rolling_window::rolling_window;
use crate::planner::tests::helpers::{days, timestamp};
use crate::planner::tests::test_types::RollingWindowTestCase;

#[test]
fn given_invocation_clock_when_rolling_window_then_window_ends_at_floored_clock() {
    let test_cases = [
        RollingWindowTestCase {
            description: "day grain floors to midnight and steps back",
            days: 2,
            grain: Grain::Day,
            expected_window: (timestamp(1, 29, 0, 0), timestamp(1, 31, 0, 0)),
        },
        RollingWindowTestCase {
            description: "hour grain keeps the hour",
            days: 1,
            grain: Grain::Hour,
            expected_window: (timestamp(1, 30, 12, 0), timestamp(1, 31, 12, 0)),
        },
        RollingWindowTestCase {
            description: "zero span over minute grain is empty",
            days: 0,
            grain: Grain::Minute,
            expected_window: (timestamp(1, 31, 12, 30), timestamp(1, 31, 12, 30)),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            rolling_window(
                &timestamp(1, 31, 12, 30),
                &days(test_case.days),
                test_case.grain
            ),
            Ok(test_case.expected_window),
            "{}",
            test_case.description,
        );
    }
}
