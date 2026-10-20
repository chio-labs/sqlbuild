use std::cell::Cell;

use crate::compile_context::tests::helpers::{collected, outer_attachment_ms, uncollected};
use crate::compile_context::tests::test_types::{
    NestingTestCase, RecordingTestCase, SteppingClock,
};

#[test]
fn given_recorders_when_a_compile_collects_then_only_the_active_collector_receives_them() {
    let test_cases = [
        RecordingTestCase {
            description: "a collecting compile receives every recording",
            run: collected,
            expected_elapsed_ns: Some(2_000_000),
            expected_cpu_ns: Some(5),
            expected_metric: Some(3),
            expected_wall_recorded: true,
        },
        RecordingTestCase {
            description: "recordings outside a collection are dropped",
            run: uncollected,
            expected_elapsed_ns: None,
            expected_cpu_ns: None,
            expected_metric: None,
            expected_wall_recorded: false,
        },
    ];
    for test_case in test_cases {
        let clock = SteppingClock {
            now: Cell::new(0),
            step: 5,
        };
        let timings = (test_case.run)(&clock);
        let phase = |name: &str| {
            timings
                .as_ref()
                .and_then(|t| t.elapsed_ns.get(name).copied())
        };
        assert_eq!(
            phase("attachment_ms"),
            test_case.expected_elapsed_ns,
            "{}",
            test_case.description
        );
        assert_eq!(
            phase("model_analysis_cpu_ms"),
            test_case.expected_cpu_ns,
            "{}",
            test_case.description
        );
        assert_eq!(
            timings
                .as_ref()
                .and_then(|t| t.metrics.get("analysis_cache_misses").copied()),
            test_case.expected_metric,
            "{}",
            test_case.description
        );
        assert_eq!(
            phase("test_planning_ms").is_some(),
            test_case.expected_wall_recorded,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_nested_collection_when_it_ends_then_the_outer_collector_is_active_again() {
    let test_cases = [NestingTestCase {
        description: "the inner collection's timing stays out of the outer one",
        inner_ns: 9_000_000,
        outer_ns: 1_000_000,
        expected_outer_ms: 1,
    }];
    for test_case in test_cases {
        assert_eq!(
            outer_attachment_ms(test_case.inner_ns, test_case.outer_ns),
            Some(test_case.expected_outer_ms),
            "{}",
            test_case.description
        );
    }
}
