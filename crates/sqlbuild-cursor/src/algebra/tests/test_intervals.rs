use crate::algebra::errors::CursorError;
use crate::algebra::main::render::render;
use crate::algebra::main::split_into_batches::split_into_batches;
use crate::algebra::models::{Grain, Interval};
use crate::algebra::tests::helpers::{date, integer, naive};
use crate::algebra::tests::test_types::{NoZones, SplitTestCase};

#[test]
fn given_aligned_interval_when_splitting_then_batches_cover_it() {
    let test_cases = [
        SplitTestCase {
            description: "monthly batches of two across a leap February",
            start: naive(2023, 12, 1, 0),
            end: naive(2024, 5, 1, 0),
            grain: Some(Grain::Month),
            step: 2,
            expected_starts: Ok(vec![
                "2023-12-01T00:00:00".to_owned(),
                "2024-02-01T00:00:00".to_owned(),
                "2024-04-01T00:00:00".to_owned(),
            ]),
        },
        SplitTestCase {
            description: "a single short day batch",
            start: date(2024, 2, 29),
            end: date(2024, 3, 1),
            grain: Some(Grain::Day),
            step: 7,
            expected_starts: Ok(vec!["2024-02-29".to_owned()]),
        },
        SplitTestCase {
            description: "integer batches",
            start: integer(0),
            end: integer(5),
            grain: None,
            step: 2,
            expected_starts: Ok(vec!["0".to_owned(), "2".to_owned(), "4".to_owned()]),
        },
        SplitTestCase {
            description: "a zero step is rejected",
            start: integer(0),
            end: integer(5),
            grain: None,
            step: 0,
            expected_starts: Err(CursorError::Algebra(
                "cursor batch step must be positive".to_owned(),
            )),
        },
    ];

    for test_case in test_cases {
        let interval = Interval {
            start: test_case.start,
            end: test_case.end,
            grain: test_case.grain,
        };

        let starts = split_into_batches(&interval, test_case.step, &NoZones).map(|batches| {
            batches
                .iter()
                .map(|batch| render(&batch.start, &NoZones).unwrap_or_default())
                .collect::<Vec<_>>()
        });

        assert_eq!(
            starts, test_case.expected_starts,
            "{}",
            test_case.description
        );
    }
}
