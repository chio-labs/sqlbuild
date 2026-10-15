//! Resolve a shape class by its Python module and name: the native class once it is hosted natively.

use pyo3::exceptions::PyLookupError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};

use sqlbuild_cache::stage_capture::constants::HOSTED_SHAPE_TYPES;

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::records::constants::NATIVE_MODULE;

/// The native class name hosting `module:class`, failing when the qualified key is ambiguous.
pub(crate) fn hosted_name(module: &str, class: &str) -> PyResult<Option<&'static str>> {
    let mut found: Option<&'static str> = None;
    for (native, python) in HOSTED_SHAPE_TYPES {
        let Some((python_module, python_class)) = python.split_once(':') else {
            continue;
        };
        if python_module != module || python_class != class {
            continue;
        }
        let Some(native_name) = native
            .strip_prefix(NATIVE_MODULE)
            .and_then(|rest| rest.strip_prefix(':'))
        else {
            continue;
        };
        if found.is_some_and(|existing| existing != native_name) {
            return Err(PyLookupError::new_err(format!(
                "{module}:{class} names more than one natively hosted shape"
            )));
        }
        found = Some(native_name);
    }
    Ok(found)
}

/// `class` of the Python module object `module`, or the native class hosting it.
pub(crate) fn shape_class<'py, T>(
    module: &Bound<'py, T>,
    class: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let module_path: String = module.as_any().getattr("__name__")?.extract()?;
    if let Some(native) = hosted_name(&module_path, class)? {
        return imported(module.py(), NATIVE_MODULE, native);
    }
    module.as_any().getattr(class)
}

/// `class` of the module at `module_path`, or the native class hosting it.
pub(crate) fn shape_class_at<'py>(
    py: Python<'py>,
    module_path: &str,
    class: &str,
) -> PyResult<Bound<'py, PyAny>> {
    if let Some(native) = hosted_name(module_path, class)? {
        return imported(py, NATIVE_MODULE, native);
    }
    imported(py, module_path, class)
}
