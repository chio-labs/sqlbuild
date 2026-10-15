//! The launch record the native `sqb` executable offered this invocation.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods};

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const NATIVE_MODULE: &str = "sqlbuild._native";
/// The module attributes holding the offered path's and the withheld flag's `ContextVar`s.
const OFFERED_ATTRIBUTE: &str = "_launch_record_offered";
const WITHHELD_ATTRIBUTE: &str = "_launch_record_withheld";
const OFFERED_NAME: &str = "sqlbuild_launch_record";
const WITHHELD_NAME: &str = "sqlbuild_launch_record_withheld";

/// Remember where `sqb` looks for this invocation's launch record, or that it offered none.
pub(crate) fn offer_launch_record(py: Python<'_>, path: Option<Bound<'_, PyAny>>) -> PyResult<()> {
    let path: Bound<'_, PyAny> = path.unwrap_or_else(|| py.None().into_bound(py));
    imported(py, NATIVE_MODULE, OFFERED_ATTRIBUTE)?.call_method1("set", (path,))?;
    imported(py, NATIVE_MODULE, WITHHELD_ATTRIBUTE)?.call_method1("set", (false,))?;
    Ok(())
}

/// Withhold the launch record: `sqb` cannot replay what this invocation also depends on.
pub(crate) fn withhold_launch_record(py: Python<'_>) -> PyResult<()> {
    imported(py, NATIVE_MODULE, WITHHELD_ATTRIBUTE)?.call_method1("set", (true,))?;
    Ok(())
}

/// The offered launch record path, unless an input outside its key was read.
pub(crate) fn launch_record_path(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    if imported(py, NATIVE_MODULE, WITHHELD_ATTRIBUTE)?
        .call_method0("get")?
        .is_truthy()?
    {
        return Ok(py.None().into_bound(py));
    }
    imported(py, NATIVE_MODULE, OFFERED_ATTRIBUTE)?.call_method0("get")
}

fn context_variable<'py>(
    py: Python<'py>,
    name: &str,
    default: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let keywords: Bound<'py, PyDict> = PyDict::new(py);
    keywords.set_item("default", default)?;
    py.import("contextvars")?
        .getattr("ContextVar")?
        .call((name,), Some(&keywords))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py: Python<'_> = module.py();
    module.add(
        OFFERED_ATTRIBUTE,
        context_variable(py, OFFERED_NAME, py.None().into_bound(py))?,
    )?;
    module.add(
        WITHHELD_ATTRIBUTE,
        context_variable(
            py,
            WITHHELD_NAME,
            PyBool::new(py, false).to_owned().into_any(),
        )?,
    )
}
