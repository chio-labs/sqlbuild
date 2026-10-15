//! Resolve a shape class by its Python module and name: the native class once it is hosted natively.

use pyo3::exceptions::PyLookupError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};

use sqlbuild_cache::hosted_shapes::main::hosted_native_name::hosted_native_name;

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::records::constants::NATIVE_MODULE;

/// The native class name hosting `module:class`, failing loudly when the name is ambiguous.
fn hosted_name(module: &str, class: &str) -> PyResult<Option<&'static str>> {
    hosted_native_name(module, class).map_err(|_| {
        PyLookupError::new_err(format!(
            "{module}:{class} names more than one natively hosted shape"
        ))
    })
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
