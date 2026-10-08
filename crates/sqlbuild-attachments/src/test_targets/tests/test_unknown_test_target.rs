use crate::test_targets::main::unknown_test_target::unknown_test_target;
use crate::test_targets::tests::helpers::group;
use crate::test_targets::tests::test_types::UnknownTargetTestCase;

#[test]
fn given_test_targets_when_validating_then_python_first_error_is_returned() {
    let test_cases = [
        UnknownTargetTestCase {
            description: "known targets pass",
            groups: vec![group(
                "mocks unknown model",
                &["orders"],
                &["orders", "customers"],
            )],
            expected_error: None,
        },
        UnknownTargetTestCase {
            description: "the first unknown target of the first failing group is reported",
            groups: vec![
                group("mocks unknown model", &["orders"], &["orders"]),
                group("mocks unknown seed", &["codes", "regions"], &["regions"]),
                group("expects unknown model", &["missing"], &[]),
            ],
            expected_error: Some(
                "SQL test file tests/unit/test_orders.sql mocks unknown seed 'codes'",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            unknown_test_target("tests/unit/test_orders.sql", &test_case.groups).as_deref(),
            test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}
