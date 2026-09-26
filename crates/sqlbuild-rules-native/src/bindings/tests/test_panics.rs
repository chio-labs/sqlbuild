use crate::bindings::_helpers::panics::{NativeCompilerError, compiler_error};
use crate::bindings::tests::test_types::PanicTestCase;
use crate::bindings::types::CompilerDetach;
use pyo3::Python;

#[test]
fn given_native_unwind_when_crossing_python_boundary_then_returns_named_compiler_error() {
    let test_cases = [PanicTestCase {
        description: "panic becomes a recoverable compiler exception",
        expected_named_error: true,
    }];
    Python::initialize();
    for test_case in test_cases {
        Python::attach(|py| {
            let result: Result<(), String> =
                py.compiler_detach(|| std::panic::panic_any("synthetic compiler failure"));
            let error = result.expect_err("native panic must become an error");
            assert_eq!(
                compiler_error(error).is_instance_of::<NativeCompilerError>(py),
                test_case.expected_named_error,
                "{}",
                test_case.description
            );
        });
    }
}
