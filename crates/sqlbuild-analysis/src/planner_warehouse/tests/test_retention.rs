//! Retention directions and phases follow inspected state and rendered change phases.

use crate::planner_warehouse::main::retention_change::retention_change;
use crate::planner_warehouse::main::retention_direction::retention_direction;
use crate::planner_warehouse::main::table_type_copy_name::table_type_copy_name;
use crate::planner_warehouse::tests::test_types::{
    CopyNameTestCase, RetentionChangeTestCase, RetentionDirectionTestCase,
};

#[test]
fn given_inspected_retention_when_comparing_then_returns_direction() {
    let test_cases = [
        RetentionDirectionTestCase {
            description: "effective days below desired increase",
            delta_values: [None, None],
            effective_days: 1,
            desired_days: 7,
            expected_direction: "increase",
        },
        RetentionDirectionTestCase {
            description: "delta values on both sides are mixed",
            delta_values: [Some(3), Some(30)],
            effective_days: 7,
            desired_days: 7,
            expected_direction: "mixed",
        },
        RetentionDirectionTestCase {
            description: "delta value above desired decreases",
            delta_values: [None, Some(30)],
            effective_days: 1,
            desired_days: 7,
            expected_direction: "decrease",
        },
        RetentionDirectionTestCase {
            description: "equal days match",
            delta_values: [None, None],
            effective_days: 7,
            desired_days: 7,
            expected_direction: "match",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            retention_direction(
                test_case.delta_values,
                test_case.effective_days,
                test_case.desired_days
            ),
            test_case.expected_direction,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_rendered_change_when_phasing_then_prepare_and_finalize_override_fallback() {
    let test_cases = [
        RetentionChangeTestCase {
            description: "prepare increases first",
            change_phase: "prepare",
            fallback: "mixed",
            expected_change: ("increase", "pre"),
        },
        RetentionChangeTestCase {
            description: "finalize decreases last",
            change_phase: "finalize",
            fallback: "mixed",
            expected_change: ("decrease", "post"),
        },
        RetentionChangeTestCase {
            description: "alter increase runs before",
            change_phase: "alter",
            fallback: "increase",
            expected_change: ("increase", "pre"),
        },
        RetentionChangeTestCase {
            description: "alter decrease runs after",
            change_phase: "alter",
            fallback: "decrease",
            expected_change: ("decrease", "post"),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            retention_change(test_case.change_phase, test_case.fallback),
            test_case.expected_change,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_target_name_when_naming_copy_then_fits_identifier_limit() {
    let test_cases = [
        CopyNameTestCase {
            description: "short name keeps whole target",
            target_name: "orders",
            identifier_limit: 255,
            expected_name: "__sqb_type_swap__orders__1c168adb00d2",
        },
        CopyNameTestCase {
            description: "tight limit truncates target",
            target_name: "orders",
            identifier_limit: 34,
            expected_name: "__sqb_type_swap__ord__1c168adb00d2",
        },
        CopyNameTestCase {
            description: "limit below affixes drops target",
            target_name: "orders",
            identifier_limit: 3,
            expected_name: "__sqb_type_swap____1c168adb00d2",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            table_type_copy_name(test_case.target_name, test_case.identifier_limit),
            test_case.expected_name,
            "{}",
            test_case.description
        );
    }
}
