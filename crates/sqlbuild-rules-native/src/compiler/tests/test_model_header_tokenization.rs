use crate::compiler::tests::helpers::{
    batch_sizes_bound_workers_by_contract, invalid_headers_return_each_exact_error_in_order,
    nested_and_root_columns_return_only_root_offsets,
    nested_authored_headers_preserve_values_and_offsets,
};
use crate::compiler::tests::test_types::ModelHeaderTokenizationTestCase;

#[test]
fn given_model_header_cases_when_exercising_native_parser_then_expected_behavior_holds() {
    let test_cases = [
        ModelHeaderTokenizationTestCase {
            description: "nested authored headers preserve values and offsets",
            run: nested_authored_headers_preserve_values_and_offsets,
            expected_success: true,
        },
        ModelHeaderTokenizationTestCase {
            description: "invalid headers return exact ordered errors",
            run: invalid_headers_return_each_exact_error_in_order,
            expected_success: true,
        },
        ModelHeaderTokenizationTestCase {
            description: "nested columns do not leak into root offsets",
            run: nested_and_root_columns_return_only_root_offsets,
            expected_success: true,
        },
        ModelHeaderTokenizationTestCase {
            description: "worker count and stack size remain bounded",
            run: batch_sizes_bound_workers_by_contract,
            expected_success: true,
        },
    ];

    for test_case in test_cases {
        let actual_success = (test_case.run)();
        assert_eq!(
            actual_success, test_case.expected_success,
            "{}",
            test_case.description
        );
    }
}
