//! Convert unwinding native failures into ordinary named compiler errors.

use pyo3::Python;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::{PyErr, create_exception};

create_exception!(_native, NativeCompilerError, PyRuntimeError);
const PANIC_MESSAGE: &str = "NativeCompilerError: native SQL compilation panicked";

pub(crate) fn compiler_error(error: impl std::fmt::Display) -> PyErr {
    let message = error.to_string();
    if message == PANIC_MESSAGE {
        NativeCompilerError::new_err(message)
    } else {
        PyValueError::new_err(message)
    }
}

pub(crate) fn compiler_guard<T>(
    operation: impl FnOnce() -> pyo3::PyResult<T>,
) -> pyo3::PyResult<T> {
    match catch_unwind(AssertUnwindSafe(operation)) {
        Ok(result) => result,
        Err(_) => Err(NativeCompilerError::new_err(PANIC_MESSAGE)),
    }
}
use std::panic::{AssertUnwindSafe, catch_unwind};

use crate::bindings::types::CompilerDetach;

impl CompilerDetach for Python<'_> {
    fn compiler_detach<T: Send, F: FnOnce() -> Result<T, String> + Send>(
        self,
        operation: F,
    ) -> Result<T, String> {
        self.detach(|| match catch_unwind(AssertUnwindSafe(operation)) {
            Ok(result) => result,
            Err(_) => Err(PANIC_MESSAGE.to_owned()),
        })
    }
}
