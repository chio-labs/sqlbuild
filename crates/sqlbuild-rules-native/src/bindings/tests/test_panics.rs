use crate::bindings::_helpers::panics::{catch_compiler_panic, is_compiler_panic};
use crate::bindings::tests::test_types::PanicTestCase;

#[test]
fn given_native_failure_when_crossing_python_boundary_then_only_unwinds_become_named_compiler_errors()
 {
    let test_cases = [
        PanicTestCase {
            description: "panic becomes a recoverable compiler exception",
            operation: || std::panic::panic_any("synthetic compiler failure"),
            expected_named_error: true,
        },
        PanicTestCase {
            description: "ordinary compiler error keeps its own message",
            operation: || Err("unknown column 'customer_id'".to_owned()),
            expected_named_error: false,
        },
    ];
    for test_case in test_cases {
        let error = catch_compiler_panic(test_case.operation)
            .expect_err("native failure must become an error");
        assert_eq!(
            is_compiler_panic(&error),
            test_case.expected_named_error,
            "{}",
            test_case.description
        );
    }
}
