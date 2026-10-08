use crate::test_targets::main::unknown_test_target::unknown_test_target;
use crate::test_targets::models::TestTargets;
use crate::test_targets::tests::helpers::{catalog, names};
use crate::test_targets::tests::test_types::UnknownTargetTestCase;

#[test]
fn given_test_targets_when_validating_then_python_first_error_is_returned() {
    let test_cases = [
        UnknownTargetTestCase {
            description: "known targets pass",
            targets: TestTargets {
                mock_models: names(&["orders"]),
                expected_models: names(&["customers"]),
                ..TestTargets::default()
            },
            expected_error: None,
        },
        UnknownTargetTestCase {
            description: "the first unknown target of the first failing group is reported",
            targets: TestTargets {
                mock_models: names(&["orders"]),
                mock_seeds: names(&["codes", "regions"]),
                expected_models: names(&["missing"]),
                ..TestTargets::default()
            },
            expected_error: Some(
                "SQL test file tests/unit/test_orders.sql mocks unknown seed 'codes'",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            unknown_test_target("tests/unit/test_orders.sql", &catalog(), &test_case.targets)
                .as_deref(),
            test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}
