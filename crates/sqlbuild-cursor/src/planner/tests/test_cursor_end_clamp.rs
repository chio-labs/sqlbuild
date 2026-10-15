use crate::planner::main::cursor_end_clamp::cursor_end_clamp;
use crate::planner::models::CursorEndClamp;
use crate::planner::tests::helpers::timestamp;
use crate::planner::tests::test_types::{CursorEndClampTestCase, UtcZones};

#[test]
fn given_window_and_cursor_end_when_clamping_then_window_never_passes_end() {
    let test_cases = [
        CursorEndClampTestCase {
            description: "window before the end is unchanged",
            start_day: 1,
            end_day: 5,
            expected_clamp: CursorEndClamp::Unchanged,
        },
        CursorEndClampTestCase {
            description: "window crossing the end is capped",
            start_day: 5,
            end_day: 15,
            expected_clamp: CursorEndClamp::Capped,
        },
        CursorEndClampTestCase {
            description: "window starting at the end is empty",
            start_day: 10,
            end_day: 15,
            expected_clamp: CursorEndClamp::Empty,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            cursor_end_clamp(
                (
                    &timestamp(1, test_case.start_day, 0, 0),
                    &timestamp(1, test_case.end_day, 0, 0)
                ),
                &timestamp(1, 10, 0, 0),
                &UtcZones,
            ),
            Ok(test_case.expected_clamp),
            "{}",
            test_case.description,
        );
    }
}
