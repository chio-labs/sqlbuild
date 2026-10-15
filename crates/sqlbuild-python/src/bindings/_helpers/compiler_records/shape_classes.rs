//! Resolve a shape class by name: the native class once it is hosted natively, else the Python one.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::compile_records::constants::COMPILE_VALUE_RECORDS;
use crate::bindings::_helpers::compiler_records::constants::{
    COMPILER_ENUMS, COMPILER_ERRORS, COMPILER_RECORDS,
};
use crate::bindings::_helpers::records::constants::NATIVE_MODULE;

/// Whether `class` is one of the compiler shapes hosted natively.
fn hosted(class: &str) -> bool {
    COMPILER_RECORDS.iter().any(|spec| spec.name == class)
        || COMPILE_VALUE_RECORDS.iter().any(|spec| spec.name == class)
        || COMPILER_ENUMS.iter().any(|spec| spec.name == class)
        || COMPILER_ERRORS.iter().any(|spec| spec.name == class)
}

/// `class` from the native module when hosted natively, else from the imported `module`.
pub(crate) fn shape_class<'py, T>(
    module: &Bound<'py, T>,
    class: &str,
) -> PyResult<Bound<'py, PyAny>> {
    if hosted(class) {
        return imported(module.py(), NATIVE_MODULE, class);
    }
    module.as_any().getattr(class)
}

/// `class` from the native module when hosted natively, else from the module at `module_path`.
pub(crate) fn shape_class_at<'py>(
    py: Python<'py>,
    module_path: &str,
    class: &str,
) -> PyResult<Bound<'py, PyAny>> {
    if hosted(class) {
        return imported(py, NATIVE_MODULE, class);
    }
    imported(py, module_path, class)
}
