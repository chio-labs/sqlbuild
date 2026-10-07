//! Convert unwinding native failures into ordinary named compiler errors.

use pyo3::Python;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::{PyErr, create_exception};
use sqlbuild_core::constants::PANIC_MESSAGE;
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;
use sqlbuild_core::panics::main::is_compiler_panic::is_compiler_panic;
use std::panic::{AssertUnwindSafe, catch_unwind};

use crate::bindings::types::CompilerDetach;

create_exception!(_native, NativeCompilerError, PyRuntimeError);

pub(crate) fn compiler_error(error: impl std::fmt::Display) -> PyErr {
    let message = error.to_string();
    if is_compiler_panic(&message) {
        NativeCompilerError::new_err(message)
    } else {
        PyValueError::new_err(message)
    }
}

pub(crate) fn value_error(error: impl std::fmt::Display) -> PyErr {
    compiler_error(error)
}

pub(crate) fn compiler_guard<T>(
    operation: impl FnOnce() -> pyo3::PyResult<T>,
) -> pyo3::PyResult<T> {
    match catch_unwind(AssertUnwindSafe(operation)) {
        Ok(result) => result,
        Err(_) => Err(NativeCompilerError::new_err(PANIC_MESSAGE)),
    }
}

impl CompilerDetach for Python<'_> {
    fn compiler_detach<T: Send, F: FnOnce() -> Result<T, String> + Send>(
        self,
        operation: F,
    ) -> Result<T, String> {
        self.detach(|| catch_compiler_panic(operation))
    }
}
